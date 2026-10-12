"""
db.py — 予定データの保存・読み出しと、終わった予定の自動削除

【このファイルの役割】
- 予定を SQLite（data/events.db）に保存・読み出し・修正・削除する
- 「毎年繰り返す予定」の次の発生日を計算する
- 終わった予定（繰り返さないもの）をまとめて削除する

SQLite は Python に最初から入っている sqlite3 モジュールで扱えるので、
追加のインストールは不要です。データは1つのファイルに保存されるため、
プログラムを閉じても Mac mini を再起動しても予定は消えません。

【予定1件のデータ（events テーブルの列）】
    id          … 自動で振られる番号
    title       … タイトル（必須）
    date        … 日付 "YYYY-MM-DD"（必須）。毎年繰り返す予定では「最初の日付」
    start_time  … 開始時刻 "HH:MM"（空なら終日）
    end_time    … 終了時刻 "HH:MM"（空でもよい）
    important   … 重要なら 1、そうでなければ 0
    yearly      … 毎年繰り返すなら 1、そうでなければ 0
    author      … 登録者名（空でもよい）
    memo        … メモ（空でもよい）
    created_at / updated_at … 登録・更新した日時（記録用）
"""

import sqlite3
from datetime import date, datetime, time, timedelta

import config

# 予定を外に渡すときに使う列名の一覧（この順で辞書にします）
COLUMNS = [
    "id",
    "title",
    "date",
    "start_time",
    "end_time",
    "important",
    "yearly",
    "author",
    "memo",
    "created_at",
    "updated_at",
]


# ===========================================================================
# 接続と初期化
# ===========================================================================


def connect():
    """
    SQLite データベースに接続して、接続オブジェクトを返す。

    Flask はリクエストごとに別のスレッドで動くことがあり、SQLite の接続は
    スレッドをまたいで使い回せないため、「使うたびに接続して、終わったら閉じる」
    という単純な方式にしています（部室で使う程度なら速度は問題になりません）。
    """
    # data フォルダがなければ作る（初回起動時など）
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    # row_factory を設定すると、行を row["title"] のように列名で読めるようになる
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """
    テーブルがなければ作る。サーバー起動時に1回呼ぶ。

    「CREATE TABLE IF NOT EXISTS」なので、すでにデータがある場合は何もしません
    （= 何度呼んでもデータは消えません）。
    """
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT    NOT NULL,
                date        TEXT    NOT NULL,
                start_time  TEXT,
                end_time    TEXT,
                important   INTEGER NOT NULL DEFAULT 0,
                yearly      INTEGER NOT NULL DEFAULT 0,
                author      TEXT    NOT NULL DEFAULT '',
                memo        TEXT    NOT NULL DEFAULT '',
                created_at  TEXT    NOT NULL,
                updated_at  TEXT    NOT NULL
            )
            """
        )
    conn.close()


def _row_to_dict(row):
    """sqlite3.Row を普通の辞書に変換する（JSON にしやすくするため）。"""
    d = {col: row[col] for col in COLUMNS}
    # 0/1 で保存しているものは True/False にしておくと JavaScript 側で扱いやすい
    d["important"] = bool(d["important"])
    d["yearly"] = bool(d["yearly"])
    return d


def _now_text():
    """記録用の現在日時の文字列（例: 2026-10-12 13:45:00）。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ===========================================================================
# 読み書き（一覧・1件取得・追加・修正・削除）
# ===========================================================================


def list_events():
    """保存されているすべての予定を、辞書のリストで返す。"""
    conn = connect()
    try:
        rows = conn.execute("SELECT * FROM events ORDER BY date, start_time").fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def get_event(event_id):
    """id で予定を1件取り出す。見つからなければ None を返す。"""
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def create_event(data):
    """
    予定を1件追加して、振られた id を返す。

    data は app.py でチェック済みの辞書（title, date, start_time, end_time,
    important, yearly, author, memo）を想定しています。
    """
    now = _now_text()
    conn = connect()
    try:
        with conn:  # with を使うと、成功時に自動でコミット（保存）される
            cur = conn.execute(
                """
                INSERT INTO events
                    (title, date, start_time, end_time, important, yearly,
                     author, memo, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["title"],
                    data["date"],
                    data["start_time"],
                    data["end_time"],
                    int(data["important"]),
                    int(data["yearly"]),
                    data["author"],
                    data["memo"],
                    now,
                    now,
                ),
            )
            return cur.lastrowid
    finally:
        conn.close()


def update_event(event_id, data):
    """
    予定を修正する。修正できたら True、その id がなければ False を返す。

    毎年繰り返す予定も「1件のデータ」として保存しているので、
    ここで修正すればすべての年の表示に反映されます。
    """
    conn = connect()
    try:
        with conn:
            cur = conn.execute(
                """
                UPDATE events
                SET title = ?, date = ?, start_time = ?, end_time = ?,
                    important = ?, yearly = ?, author = ?, memo = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    data["title"],
                    data["date"],
                    data["start_time"],
                    data["end_time"],
                    int(data["important"]),
                    int(data["yearly"]),
                    data["author"],
                    data["memo"],
                    _now_text(),
                    event_id,
                ),
            )
            return cur.rowcount > 0
    finally:
        conn.close()


def delete_event(event_id):
    """予定を削除する。削除できたら True、その id がなければ False を返す。"""
    conn = connect()
    try:
        with conn:
            cur = conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
            return cur.rowcount > 0
    finally:
        conn.close()


# ===========================================================================
# 日付の計算（毎年繰り返す予定・終了判定）
# ===========================================================================


def _parse_date(text):
    """"YYYY-MM-DD" の文字列を date に変換する。"""
    return datetime.strptime(text, "%Y-%m-%d").date()


def _parse_time(text):
    """"HH:MM" の文字列を time に変換する。"""
    return datetime.strptime(text, "%H:%M").time()


def date_in_year(original, year):
    """
    毎年繰り返す予定について、指定した年での日付を返す。

    2/29 の予定は、うるう年でない年には 2/28 に表示する（仕様書 5章）。
    それ以外は単純に年だけを差し替えます。
    """
    try:
        return original.replace(year=year)
    except ValueError:
        # replace で失敗するのは「うるう年でない年の 2/29」だけ
        return date(year, 2, 28)


def end_datetime(event, day):
    """
    予定が day の日に行われたとして、「終わる日時」を返す。

    - 終了時刻があれば、その日のその時刻に終わる
    - 終了時刻がなければ（終日の予定や、開始時刻だけの予定）、その日いっぱい
      （= 翌日の 0:00）まで表示する
    """
    if event["end_time"]:
        return datetime.combine(day, _parse_time(event["end_time"]))
    return datetime.combine(day + timedelta(days=1), time(0, 0))


def next_occurrence(event, now=None):
    """
    予定の「次に表示すべき日付」を返す。もう終わっていて表示しない場合は None。

    - 繰り返さない予定：登録した日付。終わっていれば None
    - 毎年繰り返す予定：今年の分がまだ終わっていなければ今年の日付、
      終わっていれば来年の日付。
      ただし「来年から始まる」予定を今年に表示しないよう、登録した年より前には戻らない。
    """
    if now is None:
        now = datetime.now()
    original = _parse_date(event["date"])

    if not event["yearly"]:
        return original if end_datetime(event, original) > now else None

    year = max(now.year, original.year)
    candidate = date_in_year(original, year)
    if end_datetime(event, candidate) <= now:
        candidate = date_in_year(original, year + 1)
    return candidate


def upcoming_events(now=None):
    """
    まだ終わっていない予定を、次の発生日の近い順に並べて返す。

    各予定の辞書には "next_date"（"YYYY-MM-DD"、次に行われる日）を追加します。
    モニター画面の「あと○日」は、この next_date と今日の日付の差で計算します。

    並び順：日付 → 終日の予定を先に → 開始時刻 → タイトル
    """
    if now is None:
        now = datetime.now()
    result = []
    for ev in list_events():
        nxt = next_occurrence(ev, now)
        if nxt is None:
            continue  # もう終わった予定（自動削除される前のもの）は表示しない
        ev["next_date"] = nxt.isoformat()
        result.append(ev)
    # 開始時刻が空（終日）の予定は "" になるので、同じ日の中で先頭に来る
    result.sort(key=lambda e: (e["next_date"], e["start_time"] or "", e["title"]))
    return result


def days_with_events(year, month):
    """
    指定した年・月で「予定がある日」の日にち（1〜31）を、昇順のリストで返す。
    ミニ月カレンダーで印を付けるのに使います。

    毎年繰り返す予定は、その年の日付（2/29 → 2/28 の調整込み）で数えます。
    """
    days = set()
    for ev in list_events():
        original = _parse_date(ev["date"])
        if ev["yearly"]:
            if year < original.year:
                continue  # まだ始まっていない年には印を付けない
            d = date_in_year(original, year)
        else:
            d = original
        if d.year == year and d.month == month:
            days.add(d.day)
    return sorted(days)


# ===========================================================================
# 自動削除
# ===========================================================================


def delete_finished_events(now=None):
    """
    終わった予定のうち、「毎年繰り返さない」ものをまとめて削除する。
    削除した件数を返す。

    毎年繰り返す予定は、終わっても翌年また表示するので削除しません。
    app.py から、サーバー起動時と一定間隔ごと（config.CLEANUP_INTERVAL_SECONDS）に
    呼ばれます。
    """
    if now is None:
        now = datetime.now()
    finished_ids = [
        ev["id"]
        for ev in list_events()
        if not ev["yearly"] and next_occurrence(ev, now) is None
    ]
    if not finished_ids:
        return 0
    conn = connect()
    try:
        with conn:
            conn.executemany(
                "DELETE FROM events WHERE id = ?", [(i,) for i in finished_ids]
            )
    finally:
        conn.close()
    return len(finished_ids)
