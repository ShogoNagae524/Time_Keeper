#!/bin/bash
# =============================================================================
# start_kiosk.command — Mac mini の自動起動用スクリプト
#
# 【このファイルの役割】
#   1. サーバー（uv run app.py）を起動する
#   2. サーバーが応答するまで待つ
#   3. Chrome をキオスクモード（全画面・操作バーなし）で /display に開く
#
# macOS の「システム設定 → 一般 → ログイン項目」にこのファイルを追加すると、
# Mac mini にログインしたとき自動で実行されます（手順は README.md 参照）。
# 最初に一度だけ、ターミナルで `chmod +x start_kiosk.command` を実行してください。
# =============================================================================

# このファイルが置いてあるフォルダ（= プロジェクトのフォルダ）に移動する
cd "$(dirname "$0")" || exit 1

# ログイン直後は PATH に uv が入っていないことがあるので、よくある場所を足しておく
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

# config.py と同じポート番号にする
PORT=8000
URL="http://localhost:${PORT}/display"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# --- 1. サーバーを起動（ログは data/server.log に残す） ---
mkdir -p data
uv run app.py >> data/server.log 2>&1 &
SERVER_PID=$!

# --- 2. サーバーが応答するまで最大60秒待つ ---
for i in $(seq 1 60); do
  if curl -s -o /dev/null "$URL"; then
    break
  fi
  sleep 1
done

# --- 3. Chrome をキオスクモードで開く ---
#   --kiosk                          : 全画面・アドレスバーなし
#   --noerrdialogs                   : エラーのポップアップを出さない
#   --disable-session-crashed-bubble : 「正しく終了しませんでした」を出さない
#   --user-data-dir                  : 普段使いの Chrome と設定を分ける
"$CHROME" \
  --kiosk \
  --noerrdialogs \
  --disable-session-crashed-bubble \
  --disable-infobars \
  --user-data-dir="$HOME/.time_keeper_chrome" \
  "$URL" &

# サーバーが終わるまでこのスクリプトも待つ（ターミナルを閉じるとサーバーも止まる）
wait $SERVER_PID
