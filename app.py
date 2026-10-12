"""
app.py — Flask サーバー本体（ページと API）

【このファイルの役割】
Mac mini 上で動く Web サーバーです。次のページと API を提供します。

    /                       … スマホ用の入力画面（一覧・追加・修正・削除）
    /display                … モニター用の画面（アナログ時計＋カレンダー）
    /qr.svg                 … 入力画面の URL を入れた QR コード画像
    /api/events             … GET: 予定の一覧 / POST: 予定の追加
    /api/events/<id>        … PUT: 予定の修正 / DELETE: 予定の削除
    /api/display            … モニター画面用にまとめたデータ（今後の予定・重要な予定など）

【起動のしかた】
    uv run app.py

起動すると、ターミナルに「スマホ用 URL」が表示されます。
"""

import io
import socket
import threading
from datetime import date, datetime

import segno
from flask import Flask, Response, abort, jsonify, render_template, request

import config
import db

app = Flask(__name__)


# ===========================================================================
# 起動時の準備（IP アドレスと QR コード）
# ===========================================================================


def get_local_ip():
    """
    この Mac mini の LAN 内の IP アドレス（例: 192.168.1.20）を調べて返す。

    UDP ソケットを外部アドレスに「接続」すると、OS がそこへ行くのに使う
    ネットワーク（= Wi-Fi など）の IP アドレスを選んでくれます。
    UDP の connect は実際にはデータを送らないので、インターネットにつながって
    いなくても動きます。うまくいかない場合は 127.0.0.1 を返します。
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def build_edit_url():
    """
    QR コードに入れる「入力画面の URL」を作る。

    Mac mini の IP アドレスは Wi-Fi につなぎ直すと変わることがあるので、
    毎回サーバー起動時の IP から作ります（仕様書 3.3）。
    config.PUBLIC_URL が設定されていればそちらを優先します。
    """
    if config.PUBLIC_URL:
        return config.PUBLIC_URL
    return f"http://{get_local_ip()}:{config.PORT}/"


# サーバー起動時に1回だけ URL と QR コードを作っておく
EDIT_URL = build_edit_url()
# segno で QR コードを SVG 画像（バイト列）にする。黒背景のモニターでも読み取れるよう、
# 白地に黒の QR コードにして周りに余白（border）を付けています。
# <img> で表示するので、xmlns 付きの完全な SVG ファイルとして書き出します。
_qr_buffer = io.BytesIO()
segno.make(EDIT_URL, error="m").save(
    _qr_buffer, kind="svg", scale=8, border=2, dark="#000", light="#fff"
)
QR_SVG = _qr_buffer.getvalue()


# ===========================================================================
# 画面（HTML）
# ===========================================================================


@app.route("/")
def edit_page():
    """スマホ用の入力画面を返す。"""
    return render_template("edit.html")


@app.route("/display")
def display_page():
    """
    モニター用の画面を返す。

    時限の設定や表示件数などは config.py の値を HTML に埋め込んで
    JavaScript（clock.js / calendar.js）に渡します。
    """
    periods = [
        {"start": start, "end": end, "label": label}
        for start, end, label in config.PERIODS
    ]
    return render_template(
        "display.html",
        periods=periods,
        no_period_label=config.NO_PERIOD_LABEL,
        refresh_seconds=config.REFRESH_SECONDS,
        edit_url=EDIT_URL,
    )


@app.route("/qr.svg")
def qr_code():
    """入力画面の URL を入れた QR コード（SVG 画像）を返す。"""
    return Response(QR_SVG, mimetype="image/svg+xml")


# ===========================================================================
# API（予定の読み書き）
# ===========================================================================


def validate_event(payload):
    """
    入力画面から送られてきた予定のデータをチェックして整える。

    戻り値は (整えたデータ, エラーメッセージのリスト)。
    エラーがなければリストは空です。

    - タイトル・日付は必須
    - 時刻は "HH:MM" 形式。開始・終了とも空なら終日
    - 終了時刻だけの入力や、終了が開始より前になっている入力はエラー
    """
    if not isinstance(payload, dict):
        return None, ["データの形式が正しくありません"]

    def text(key):
        # None や数値が来ても落ちないよう、文字列にして前後の空白を取る
        value = payload.get(key)
        return str(value).strip() if value is not None else ""

    data = {
        "title": text("title"),
        "date": text("date"),
        "start_time": text("start_time") or None,
        "end_time": text("end_time") or None,
        "important": bool(payload.get("important")),
        "yearly": bool(payload.get("yearly")),
        "author": text("author"),
        "memo": text("memo"),
    }
    errors = []

    if not data["title"]:
        errors.append("タイトルを入力してください")
    elif len(data["title"]) > 100:
        errors.append("タイトルは100文字以内にしてください")

    try:
        datetime.strptime(data["date"], "%Y-%m-%d")
    except ValueError:
        errors.append("日付を正しく入力してください")

    for key, name in (("start_time", "開始時刻"), ("end_time", "終了時刻")):
        if data[key] is None:
            continue
        try:
            # "9:5" のような入力も "09:05" にそろえて保存する（並べ替えのため）
            data[key] = datetime.strptime(data[key], "%H:%M").strftime("%H:%M")
        except ValueError:
            errors.append(f"{name}を正しく入力してください")

    if data["end_time"] and not data["start_time"]:
        errors.append("終了時刻を入れるときは開始時刻も入力してください")
    elif (
        data["start_time"]
        and data["end_time"]
        and not errors
        and data["end_time"] < data["start_time"]
    ):
        errors.append("終了時刻は開始時刻より後にしてください")

    return data, errors


@app.get("/api/events")
def api_list_events():
    """
    入力画面用：保存されている予定をすべて返す。

    「次の発生日（next_date）」も付けて、近い順に並べます。
    終わっていて自動削除を待っている予定は含めません。
    """
    return jsonify(db.upcoming_events())


@app.post("/api/events")
def api_create_event():
    """予定を1件追加する。成功したら追加した予定を返す。"""
    data, errors = validate_event(request.get_json(silent=True))
    if errors:
        return jsonify({"errors": errors}), 400
    event_id = db.create_event(data)
    return jsonify(db.get_event(event_id)), 201


@app.put("/api/events/<int:event_id>")
def api_update_event(event_id):
    """予定を修正する。毎年繰り返す予定なら、すべての年に反映される。"""
    data, errors = validate_event(request.get_json(silent=True))
    if errors:
        return jsonify({"errors": errors}), 400
    if not db.update_event(event_id, data):
        abort(404)
    return jsonify(db.get_event(event_id))


@app.delete("/api/events/<int:event_id>")
def api_delete_event(event_id):
    """予定を削除する。"""
    if not db.delete_event(event_id):
        abort(404)
    return jsonify({"ok": True})


@app.get("/api/display")
def api_display():
    """
    モニター画面用のデータをまとめて返す。

    返す内容：
        today      … サーバーの今日の日付（"YYYY-MM-DD"）
        upcoming   … 今後の予定（直近 config.UPCOMING_COUNT 件）
        important  … 上に入らなかった重要予定のうち直近 config.IMPORTANT_COUNT 件
        marked_days … 今月で予定がある日にちのリスト（ミニ月カレンダーの印用）

    「あと○日」は日付が変わったときにすぐ数え直せるよう、
    画面側（calendar.js）で next_date と今日の日付から計算します。
    """
    events = db.upcoming_events()
    upcoming = events[: config.UPCOMING_COUNT]
    upcoming_ids = {e["id"] for e in upcoming}
    important = [e for e in events if e["important"] and e["id"] not in upcoming_ids][
        : config.IMPORTANT_COUNT
    ]
    today = date.today()
    return jsonify(
        {
            "today": today.isoformat(),
            "upcoming": upcoming,
            "important": important,
            "marked_days": db.days_with_events(today.year, today.month),
        }
    )


@app.get("/api/marked_days")
def api_marked_days():
    """
    指定した年月（?year=2026&month=10）で予定がある日にちを返す。
    いまの画面では今月分しか使っていませんが、月送りを付けたくなったとき用です。
    """
    today = date.today()
    year = request.args.get("year", default=today.year, type=int)
    month = request.args.get("month", default=today.month, type=int)
    if not 1 <= month <= 12:
        abort(400)
    return jsonify(db.days_with_events(year, month))


# ===========================================================================
# 終わった予定の自動削除（定期実行）
# ===========================================================================


def cleanup_loop(stop_event):
    """
    終わった予定（繰り返さないもの）を定期的に削除し続ける。

    別スレッドで動かし、config.CLEANUP_INTERVAL_SECONDS ごとに
    db.delete_finished_events() を呼びます。stop_event.wait() を使うと
    「指定秒数待つ（途中で止める合図が来たらすぐ抜ける）」ができます。
    """
    while not stop_event.wait(config.CLEANUP_INTERVAL_SECONDS):
        try:
            deleted = db.delete_finished_events()
            if deleted:
                print(f"[自動削除] 終わった予定を {deleted} 件削除しました")
        except Exception as e:  # 削除に失敗してもサーバーは止めない
            print(f"[自動削除] エラー: {e}")


def main():
    """サーバーを起動する。"""
    db.init_db()

    # 起動時に1回、終わった予定を削除する
    deleted = db.delete_finished_events()
    print(f"[起動時] 終わった予定を {deleted} 件削除しました")

    # その後は定期的に削除する（daemon=True なのでサーバー終了時に一緒に止まる）
    stop_event = threading.Event()
    threading.Thread(target=cleanup_loop, args=(stop_event,), daemon=True).start()

    print("=" * 60)
    print(f" スマホ用（入力画面）: {EDIT_URL}")
    print(f" モニター用        : http://localhost:{config.PORT}/display")
    print("=" * 60)

    # debug=True にすると自動再起動のために2重に起動してしまうので False のまま。
    # threaded=True で複数のスマホから同時にアクセスされても順番待ちしにくくなる。
    app.run(host=config.HOST, port=config.PORT, debug=False, threaded=True)


if __name__ == "__main__":
    main()
