"""Instagramの長期アクセストークン（有効期限60日）を更新し、新しいトークンを標準出力に出す。

GitHub Actionsで毎月実行し、出力をそのまま `gh secret set IG_ACCESS_TOKEN` に渡します。
トークンはログに出さないよう、標準出力以外には表示しません。
"""
import os
import sys

import requests

token = os.environ.get("IG_ACCESS_TOKEN")
if not token:
    sys.exit("IG_ACCESS_TOKEN が設定されていません。")

r = requests.get(
    "https://graph.instagram.com/refresh_access_token",
    params={"grant_type": "ig_refresh_token", "access_token": token},
    timeout=60,
)
data = r.json()
if r.status_code != 200 or "access_token" not in data:
    msg = data.get("error", {}).get("message", r.text)
    sys.exit(f"トークンの更新に失敗しました: {msg}\n"
             "期限切れの場合は、README の手順でトークンを取り直してください。")

days = int(data.get("expires_in", 0)) // 86400
print(f"トークンを更新しました（残り約{days}日）", file=sys.stderr)
print(data["access_token"], end="")
