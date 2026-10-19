# TSC Instagram 自動投稿

筑波大の就活サークル **TSC（Tsukuba Student Community）** のInstagramに、
カルーセル投稿（縦長1080×1350の画像5枚）を **月・水・金の20時ごろ** に自動投稿する仕組みです。

```
content/posts/*.yaml  ── 投稿の文章（ここを書くだけ）
        │  render.py（画像を自動デザイン）
        ▼
output/<投稿ID>/01〜05.jpg
        │  publish.py（Instagram APIで投稿）
        ▼
Instagram  ── 投稿済みは state/posted.json に記録
```

GitHub Actions が上の流れを週3回、自動で実行します。費用は無料です。

---

## 初回セットアップ（30分ほど）

### 1. Instagramをプロアカウントにする
TSCのアカウントが「ビジネス」または「クリエイター」になっていればOKです。

### 2. Meta for Developers でアプリを作り、トークンを取得する
1. https://developers.facebook.com/ にFacebookアカウントでログインし、「マイアプリ」→「アプリを作成」
2. ユースケースで **「Instagramでメッセージとコンテンツを管理」** を選ぶ
3. 作成後、ユースケースの「カスタマイズ」→ **「Instagramログインを使用したAPI設定」** を開く
4. 「アクセストークンを生成する」でTSCのInstagramアカウントを追加
   - テスター招待が届いた場合は、Instagramアプリの「設定 → ウェブサイトのアクセス許可 → アプリとウェブサイト → テスターへの招待」で承認
5. 権限は `instagram_business_basic` と `instagram_business_content_publish` を許可
6. 表示される **InstagramユーザーID（数字）** と **アクセストークン** を控える

> アプリは「開発モード」のままで大丈夫です（自分たちのアカウントへの投稿なので、アプリ審査は不要）。

### 3. GitHubにリポジトリを作る
1. https://github.com/ で新しいリポジトリを作成。**Public（公開）** にしてください
   （Instagramが画像を取りに来るため、画像が公開URLである必要があります。投稿する画像なので公開されても問題ありません）
2. このフォルダの中身をすべてアップロード（`.github` フォルダも忘れずに）

### 4. Secrets（秘密の値）を登録する
リポジトリの「Settings → Secrets and variables → Actions → New repository secret」で3つ登録します。

| 名前 | 中身 |
|---|---|
| `IG_USER_ID` | 手順2で控えたInstagramユーザーID |
| `IG_ACCESS_TOKEN` | 手順2で控えたアクセストークン |
| `GH_PAT` | トークン自動更新用（下記） |

**GH_PATの作り方**：GitHub右上アイコン →「Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token」。
対象リポジトリをこのリポジトリだけに絞り、権限「Secrets」を **Read and write** にして作成。

> アクセストークンは60日で期限切れになりますが、毎月1日・15日に自動で更新されます。

### 5. テスト投稿する
1. リポジトリの「Actions」タブ →「Instagram自動投稿」→「Run workflow」
2. **ドライランにチェックを入れたまま** 実行 → 画像生成とキャプションをログで確認
3. 問題なければ、チェックを外して実行 → 実際に投稿されます

あとは何もしなくても、月・水・金に順番に投稿されます。

---

## 投稿を追加する

`content/posts/` に YAML ファイルを追加するだけです。**ファイル名の順番に** 投稿されます
（`006-xxx.yaml`, `007-xxx.yaml` …のように番号をつけてください）。
既存のファイルをコピーして書き換えるのがおすすめです。

- `**強調したい言葉**` → 水色のマーカーになります
- 改行は `\n`
- 一時的に投稿を飛ばしたいときは `skip: true` を追加
- 投稿のストックがなくなると、Actionsが失敗してGitHubからメールが届きます（追加の合図）

### スライドの種類

| type | 用途 | 主な項目 |
|---|---|---|
| `cover` | 1枚目の表紙 | `category` `title` `sub` `badge` `title_size` |
| `points` | 番号つきポイント（2〜3個） | `heading` `items[n,title,body]` |
| `steps` | 手順・テンプレの型 | `heading` `items[title,tag,body]` |
| `compare` | NG例 → OK例 | `heading` `bad` `good` `why` |
| `example` | 例文 | `heading` `paragraphs[tag,text]` `chars` |
| `lists` | 質問リスト・NGリスト | `heading` `groups[title,items,ng]` |
| `summary` | 最後のまとめ＋フォロー誘導 | `heading` `items` `cta` |

## 手元で画像を確認する

```bash
pip install -r requirements.txt
python -m playwright install chromium
python scripts/render.py                 # すべて生成
python scripts/render.py 006-xxx         # 1つだけ生成
```
`output/<投稿ID>/` に画像ができます（日本語フォント Noto Sans CJK JP が必要）。

## 投稿時間を変える

`.github/workflows/post.yml` の `cron` を編集します。時刻は **UTC（日本時間−9時間）** です。
例：火・木・土の21時 → `"45 11 * * 2,4,6"`

## うまくいかないとき

| 症状 | 確認すること |
|---|---|
| `画像が公開URLで取得できません` | リポジトリがPublicになっているか |
| `Invalid OAuth access token` | トークン期限切れ → 手順2で取り直してSecretsを更新 |
| `Application does not have permission` | 手順2の権限（content_publish）を許可したか |
| スケジュール実行されない | Actionsタブでワークフローが有効になっているか |
