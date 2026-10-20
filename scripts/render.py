"""投稿内容（content/posts/*.yaml）からInstagram用のカルーセル画像を生成する。

使い方:
    python scripts/render.py            # すべての投稿を生成
    python scripts/render.py 003-gakuchika   # 指定した投稿だけ生成

出力: output/<投稿ID>/01.jpg, 02.jpg, ...（1080x1350 / JPEG）
"""
from __future__ import annotations

import base64
import html
import re
import sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = ROOT / "content" / "posts"
OUTPUT_DIR = ROOT / "output"
TEMPLATE_DIR = ROOT / "templates"
LOGO = ROOT / "assets" / "logo.png"

WIDTH, HEIGHT = 1080, 1350  # Instagramの縦長（4:5）


def md(text) -> Markup:
    """**強調** → 水色マーカー、改行 → <br>。それ以外はHTMLエスケープ。"""
    if text is None:
        return Markup("")
    s = html.escape(str(text).strip())
    s = re.sub(r"\*\*(.+?)\*\*", r'<span class="hl">\1</span>', s)
    s = s.replace("\n", "<br>")
    return Markup(s)


def load_post(path: Path) -> dict:
    post = yaml.safe_load(path.read_text(encoding="utf-8"))
    post.setdefault("id", path.stem)
    return post


def all_posts() -> list[dict]:
    return [load_post(p) for p in sorted(CONTENT_DIR.glob("*.yaml"))]


def render_post(post: dict, page, template, logo_uri: str) -> list[Path]:
    out_dir = OUTPUT_DIR / post["id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.jpg"):
        old.unlink()

    slides = post["slides"]
    if not 2 <= len(slides) <= 10:
        raise ValueError(f"{post['id']}: カルーセルは2〜10枚にしてください（現在{len(slides)}枚）")

    paths = []
    for i, slide in enumerate(slides, start=1):
        html_str = template.render(
            post=post, slide=slide, index=i, total=len(slides), logo=logo_uri
        )
        page.set_content(html_str, wait_until="load")
        page.evaluate("document.fonts.ready")
        path = out_dir / f"{i:02d}.jpg"
        page.screenshot(path=str(path), type="jpeg", quality=92,
                        clip={"x": 0, "y": 0, "width": WIDTH, "height": HEIGHT})
        paths.append(path)
    return paths


def render(post_ids: list[str] | None = None) -> dict[str, list[Path]]:
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=True)
    env.filters["md"] = md
    template = env.get_template("slide.html.j2")
    logo_uri = "data:image/png;base64," + base64.b64encode(LOGO.read_bytes()).decode()

    posts = all_posts()
    if post_ids:
        posts = [p for p in posts if p["id"] in post_ids]
        missing = set(post_ids) - {p["id"] for p in posts}
        if missing:
            raise SystemExit(f"投稿が見つかりません: {', '.join(sorted(missing))}")

    results = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=1)
        for post in posts:
            results[post["id"]] = render_post(post, page, template, logo_uri)
            print(f"✓ {post['id']}: {len(results[post['id']])}枚")
        browser.close()
    return results


if __name__ == "__main__":
    render(sys.argv[1:] or None)
