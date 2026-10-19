"""次に投稿する予定の投稿を選び、Instagram Graph APIでカルーセル投稿する。

GitHub Actionsから以下の順に呼ばれます（手元で試すこともできます）。

    python scripts/publish.py next
        → まだ投稿していない最初の投稿IDを表示

    python scripts/publish.py publish <投稿ID> --image-base-url <URL> [--dry-run]
        → output/<投稿ID>/*.jpg を <URL>/output/<投稿ID>/NN.jpg として投稿し、
          state/posted.json に記録する

必要な環境変数（GitHubのSecretsに登録）:
    IG_USER_ID       InstagramのユーザーID（数字）
    IG_ACCESS_TOKEN  長期アクセストークン
任意:
    IG_API_VERSION   既定 v24.0
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = ROOT / "content" / "posts"
OUTPUT_DIR = ROOT / "output"
STATE_FILE = ROOT / "state" / "posted.json"
JST = timezone(timedelta(hours=9))

API_VERSION = os.environ.get("IG_API_VERSION", "v24.0")
API_BASE = f"https://graph.instagram.com/{API_VERSION}"


# ---------------------------------------------------------------- 状態管理
def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"posted": []}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_post(post_id: str) -> dict:
    path = CONTENT_DIR / f"{post_id}.yaml"
    if not path.exists():
        sys.exit(f"投稿ファイルがありません: {path}")
    post = yaml.safe_load(path.read_text(encoding="utf-8"))
    post.setdefault("id", post_id)
    return post


def next_post_id() -> str | None:
    """ファイル名順で、まだ投稿していない最初の投稿（skip: true は除く）。"""
    done = {p["id"] for p in load_state()["posted"]}
    for path in sorted(CONTENT_DIR.glob("*.yaml")):
        post = yaml.safe_load(path.read_text(encoding="utf-8"))
        pid = post.get("id", path.stem)
        if pid not in done and not post.get("skip"):
            return pid
    return None


def build_caption(post: dict) -> str:
    caption = post.get("caption", "").strip()
    tags = post.get("hashtags") or []
    if tags:
        caption += "\n\n" + " ".join("#" + t.lstrip("#") for t in tags)
    if len(caption) > 2200:
        sys.exit(f"キャプションが長すぎます（{len(caption)}文字 / 上限2200）")
    if len(tags) > 30:
        sys.exit(f"ハッシュタグが多すぎます（{len(tags)}個 / 上限30）")
    return caption


# ---------------------------------------------------------------- API
class InstagramAPI:
    def __init__(self, user_id: str, token: str):
        self.user_id = user_id
        self.token = token

    def _call(self, method: str, path: str, **params) -> dict:
        params["access_token"] = self.token
        url = f"{API_BASE}/{path}"
        for attempt in range(3):
            if method == "GET":
                r = requests.get(url, params=params, timeout=60)
            else:
                r = requests.post(url, data=params, timeout=60)
            if r.status_code < 500:
                break
            time.sleep(5 * (attempt + 1))  # Meta側の一時的なエラーは再試行
        data = r.json() if r.content else {}
        if r.status_code >= 400 or "error" in data:
            err = data.get("error", {})
            raise RuntimeError(
                f"Instagram APIエラー（{r.status_code}）: {err.get('message', r.text)}"
                f" [type={err.get('type')}, code={err.get('code')}, subcode={err.get('error_subcode')}]"
            )
        return data

    def wait_until_ready(self, container_id: str, timeout_s: int = 300) -> None:
        deadline = time.time() + timeout_s
        while True:
            status = self._call("GET", container_id, fields="status_code").get("status_code")
            if status in ("FINISHED", "PUBLISHED"):
                return
            if status in ("ERROR", "EXPIRED"):
                raise RuntimeError(f"メディアの処理に失敗しました（{container_id}: {status}）")
            if time.time() > deadline:
                raise RuntimeError(f"メディアの処理がタイムアウトしました（{container_id}）")
            time.sleep(5)

    def publish_carousel(self, image_urls: list[str], caption: str) -> str:
        children = []
        for i, url in enumerate(image_urls, start=1):
            c = self._call("POST", f"{self.user_id}/media", image_url=url, is_carousel_item="true")
            print(f"  画像 {i}/{len(image_urls)} をアップロード: {c['id']}")
            children.append(c["id"])
        for cid in children:
            self.wait_until_ready(cid)

        parent = self._call(
            "POST", f"{self.user_id}/media",
            media_type="CAROUSEL", children=",".join(children), caption=caption,
        )
        self.wait_until_ready(parent["id"])
        published = self._call("POST", f"{self.user_id}/media_publish", creation_id=parent["id"])
        return published["id"]

    def permalink(self, media_id: str) -> str | None:
        try:
            return self._call("GET", media_id, fields="permalink").get("permalink")
        except RuntimeError:
            return None


# ---------------------------------------------------------------- 実行
def wait_for_public_images(urls: list[str], timeout_s: int = 120) -> None:
    """Instagramが取得しに来る前に、画像URLが公開されているか確認する。"""
    deadline = time.time() + timeout_s
    for url in urls:
        while True:
            try:
                r = requests.head(url, timeout=20, allow_redirects=True)
                if r.status_code == 200:
                    break
            except requests.RequestException:
                pass
            if time.time() > deadline:
                sys.exit(f"画像が公開URLで取得できません: {url}\n"
                         "リポジトリが公開（Public）になっているか確認してください。")
            time.sleep(5)


def cmd_publish(post_id: str, image_base_url: str, dry_run: bool) -> None:
    state = load_state()
    if any(p["id"] == post_id for p in state["posted"]):
        sys.exit(f"{post_id} は投稿済みです（state/posted.json）")

    post = load_post(post_id)
    images = sorted((OUTPUT_DIR / post_id).glob("*.jpg"))
    if not 2 <= len(images) <= 10:
        sys.exit(f"{post_id}: 画像が{len(images)}枚です。先に render.py を実行してください（2〜10枚）")

    base = image_base_url.rstrip("/")
    urls = [f"{base}/output/{post_id}/{p.name}" for p in images]
    caption = build_caption(post)

    print(f"投稿: {post_id}（{len(urls)}枚）")
    for u in urls:
        print("  " + u)
    print("--- キャプション ---\n" + caption + "\n-------------------")

    if dry_run:
        print("ドライランのため、投稿はしていません。")
        return

    user_id = os.environ.get("IG_USER_ID")
    token = os.environ.get("IG_ACCESS_TOKEN")
    if not user_id or not token:
        sys.exit("環境変数 IG_USER_ID と IG_ACCESS_TOKEN を設定してください。")

    wait_for_public_images(urls)
    api = InstagramAPI(user_id, token)
    media_id = api.publish_carousel(urls, caption)
    link = api.permalink(media_id)

    state["posted"].append({
        "id": post_id,
        "media_id": media_id,
        "permalink": link,
        "posted_at": datetime.now(JST).isoformat(timespec="seconds"),
    })
    save_state(state)
    print(f"✅ 投稿しました: {link or media_id}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("next", help="次に投稿する投稿IDを表示")
    p = sub.add_parser("publish", help="カルーセル投稿する")
    p.add_argument("post_id")
    p.add_argument("--image-base-url", required=True,
                   help="例: https://raw.githubusercontent.com/<owner>/<repo>/<commit>")
    p.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.cmd == "next":
        pid = next_post_id()
        if not pid:
            sys.exit("投稿のストックがありません。content/posts/ に新しい投稿を追加してください。")
        print(pid)
    else:
        cmd_publish(args.post_id, args.image_base_url, args.dry_run)


if __name__ == "__main__":
    main()
