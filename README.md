# 部室モニター表示システム（Time Keeper）

部室のモニターに **アナログ時計** と **部の予定** を常に表示します。
予定は部員がスマホからモニターの **QR コード** を読み取って追加・修正・削除できます。

- サーバーは Mac mini 1台で動き、部室の Wi-Fi（LAN）内で完結します（インターネット不要）
- 認証はありません。誰でも予定を編集できます
- 詳しい仕様は `部室モニター表示システム 仕様書.md` を見てください

---

## 1. 起動のしかた

### 準備（最初の1回だけ）

1. Mac mini に [uv](https://docs.astral.sh/uv/) と Google Chrome を入れる
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
2. このフォルダを Mac mini に置く（例: `~/Time_Keeper`）

### 手動で起動する

```bash
cd ~/Time_Keeper
uv run app.py
```

初回は必要なライブラリ（Flask, segno）が自動でインストールされます。
起動するとターミナルにこう表示されます。

```
 スマホ用（入力画面）: http://192.168.1.20:8000/
 モニター用        : http://localhost:8000/display
```

- モニターでは `http://localhost:8000/display` を開く
- スマホでは画面右下の QR コードを読み取る（または上の URL を開く）
- 止めるときはターミナルで `Ctrl + C`

### つながらないとき

- スマホと Mac mini が **同じ Wi-Fi** につながっているか確認する
- Wi-Fi によっては端末同士の通信が禁止されています（ゲスト用 Wi-Fi など）。その場合は部室専用の Wi-Fi ルーターを置いてください
- macOS のファイアウォールで「受信接続を許可しますか？」と出たら「許可」を押す

---

## 2. 自動起動の設定（Mac mini の電源を入れたら自動で表示）

`start_kiosk.command` が「サーバー起動 → Chrome をキオスクモードで `/display` に開く」までを行います。
（Safari はキオスクモードで起動できないので Chrome を使います）

1. ターミナルで実行権限を付ける（最初の1回だけ）
   ```bash
   cd ~/Time_Keeper
   chmod +x start_kiosk.command
   ```
2. ダブルクリックして動くか試す（Chrome が全画面で時計を表示すれば OK）
3. **システム設定 → 一般 → ログイン項目** の「ログイン時に開く」の「＋」から `start_kiosk.command` を追加
4. 自動ログインを有効にしておくと、停電などで再起動しても勝手に復帰します
   （**システム設定 → ユーザとグループ → 自動ログイン**）

キオスクモードの Chrome を終了するには `⌘ + Q` を押します。
サーバーのログは `data/server.log` に残ります。

> ポート番号を変えたときは、`config.py` の `PORT` と `start_kiosk.command` の `PORT` の両方を変えてください。

---

## 3. ファイルの構成

| パス | 役割 |
| --- | --- |
| `pyproject.toml` / `uv.lock` | uv の依存関係（Flask, segno） |
| `README.md` | このファイル |
| `config.py` | 表示件数・時限・ポート番号などの設定 |
| `app.py` | Flask サーバー本体（ページと API） |
| `db.py` | SQLite の読み書きと自動削除、毎年の予定の日付計算 |
| `templates/display.html` | モニター用の画面 |
| `templates/edit.html` | スマホ用の入力画面（画面の動きもこの中に書いてある） |
| `static/clock.js` | アナログ時計と時限表示 |
| `static/calendar.js` | ミニ月カレンダーと予定リスト |
| `static/style.css` | 見た目 |
| `start_kiosk.command` | Mac mini の自動起動用スクリプト |
| `data/events.db` | 予定データ（自動で作られる。消すと予定が全部消える） |

### ページと API

| URL | 内容 |
| --- | --- |
| `/` | スマホ用の入力画面 |
| `/display` | モニター用の画面 |
| `/qr.svg` | 入力画面の QR コード |
| `GET /api/events` | 予定の一覧（次の発生日 `next_date` 付き、近い順） |
| `POST /api/events` | 予定の追加 |
| `PUT /api/events/<id>` | 予定の修正 |
| `DELETE /api/events/<id>` | 予定の削除 |
| `GET /api/display` | モニター用にまとめたデータ |

---

## 4. よくある改変のしかた

変更したあとはサーバーを再起動（`Ctrl + C` → `uv run app.py`）してください。
画面（HTML/CSS/JS）だけの変更なら、モニターのページを再読み込み（`⌘ + R`）すれば反映されます。

### 表示件数を変えたい
`config.py` の `UPCOMING_COUNT`（今後の予定、初期値 7）と `IMPORTANT_COUNT`（重要な予定、初期値 3）を変える。

### 時限の時刻を変えたい / 6限を足したい
`config.py` の `PERIODS` を編集する。1行が1つの時間帯です。
```python
PERIODS = [
    ("9:00", "10:40", "1限"),
    ...
    ("17:10", "18:50", "5限"),
    ("18:50", "19:00", "休憩時間"),   # ← 追加
    ("19:00", "20:40", "6限"),        # ← 追加
]
```
どれにも当てはまらない時間の表示は `NO_PERIOD_LABEL`（初期値 `no schedule`）。

### 終わった予定を消す間隔を変えたい
`config.py` の `CLEANUP_INTERVAL_SECONDS`（秒、初期値 3600 = 1時間）。

### モニターに反映されるまでの時間を短くしたい
`config.py` の `REFRESH_SECONDS`（秒、初期値 30）。

### 色を変えたい
`static/style.css` の先頭の `:root { ... }` にある色を変える。
例：重要予定の色は `--accent`。

### 時計の大きさ・針の太さを変えたい
`static/style.css` の `.clock`（大きさ）、`.hand-hour` / `.hand-minute`（太さ）。
針の長さは `templates/display.html` の `hand-hour` / `hand-minute` の `y2` の値（-100 で文字盤のふちまで）。

### QR コードの URL がおかしい（違う IP になる）
Mac mini に複数のネットワーク（有線と Wi-Fi など）があると、違う IP が選ばれることがあります。
`config.py` の `PUBLIC_URL` に正しい URL を直接書いてください。
```python
PUBLIC_URL = "http://192.168.1.20:8000/"
```

### 予定データをバックアップしたい
`data/events.db` をコピーしておけば OK です。戻すときはサーバーを止めてから上書きします。

---

## 5. 予定の表示ルール（仕様のまとめ）

- 終わっていない予定だけを表示（終日の予定はその日いっぱい表示）
- 「毎年繰り返す」予定は次に来る日付で表示し、終わっても削除しない
  - 2/29 の予定は、うるう年でない年は 2/28 に表示
- 繰り返さない予定は、終わったらサーバー起動時と1時間ごとに自動で削除
- 「あと○日」は日付の差で数える（今日は「あと0日」）。0時を過ぎると自動で数え直す
- 時限表示は時刻だけで判定（土日・祝日も同じ）。終了時刻ちょうどで次の表示に切り替わる
