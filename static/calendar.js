/*
 * calendar.js — ミニ月カレンダーと予定リスト（モニター画面用）
 *
 * 【このファイルの役割】
 *   - サーバーの /api/display から予定を定期的に取り直す（入力がすぐ反映されるように）
 *   - 上段：ミニ月カレンダー（今日を強調、予定のある日に印）
 *   - 中段：今後の予定（重要予定は ★ 付き）
 *   - 下段：重要な予定（中段に入らなかったもの）
 *   - 各予定の右端に「あと○日」を表示し、日付が変わったら数え直す
 *
 * 何件表示するかはサーバー側（config.py の UPCOMING_COUNT / IMPORTANT_COUNT）で
 * 決めているので、ここでは届いたものをそのまま並べます。
 */

(function () {
  "use strict";

  const WEEKDAYS = ["日", "月", "火", "水", "木", "金", "土"];
  const DAY_MS = 24 * 60 * 60 * 1000;
  const config = window.APP_CONFIG;

  // 最後にサーバーから受け取ったデータ。通信に失敗したときはこれを表示し続ける
  let latestData = null;
  // 最後に描いたときの「今日」。日付が変わったかどうかの判定に使う
  let renderedToday = null;

  /** Date を "YYYY-MM-DD" の文字列にする（ブラウザのローカル時刻で）。 */
  function toDateKey(d) {
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    return d.getFullYear() + "-" + mm + "-" + dd;
  }

  /** "YYYY-MM-DD" をその日の 0:00 の Date にする。 */
  function parseDateKey(key) {
    const [y, m, d] = key.split("-").map(Number);
    return new Date(y, m - 1, d);
  }

  /**
   * 今日から予定日までの日数を返す（今日なら 0、明日なら 1）。
   * 時刻は見ずに「日付の差」で数えます（仕様書 3.4）。
   * 夏時間などで 1日が 24時間ちょうどでない場合に備えて Math.round で丸めています。
   */
  function daysUntil(dateKey) {
    const today = parseDateKey(toDateKey(new Date()));
    return Math.round((parseDateKey(dateKey) - today) / DAY_MS);
  }

  /**
   * HTML の要素を作る小さな関数。
   * 文字は textContent で入れるので、予定のタイトルに < や > が入っていても安全です。
   */
  function el(tag, className, text) {
    const e = document.createElement(tag);
    if (className) e.className = className;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  // ------------------------------------------------------------------------
  // ミニ月カレンダー
  // ------------------------------------------------------------------------

  /**
   * 今月のカレンダーを描く。
   * markedDays は予定がある日にちの配列（例: [3, 15, 28]）。
   */
  function renderMiniCalendar(markedDays) {
    const now = new Date();
    const year = now.getFullYear();
    const month = now.getMonth(); // 0 始まり（0 = 1月）
    const marked = new Set(markedDays);

    document.getElementById("cal-title").textContent = year + "年" + (month + 1) + "月";

    const grid = document.getElementById("cal-grid");
    grid.innerHTML = "";

    // 曜日の見出し（日曜・土曜は色を変えられるよう class を付ける）
    WEEKDAYS.forEach(function (w, i) {
      grid.appendChild(el("div", "cal-head" + weekendClass(i), w));
    });

    // 1日が何曜日かの分だけ、空のマスを置いて位置をずらす
    const firstWeekday = new Date(year, month, 1).getDay();
    for (let i = 0; i < firstWeekday; i++) {
      grid.appendChild(el("div", "cal-cell empty"));
    }

    // 月末の日にち（翌月の 0日 = 今月の最終日）
    const lastDay = new Date(year, month + 1, 0).getDate();
    for (let day = 1; day <= lastDay; day++) {
      const weekday = (firstWeekday + day - 1) % 7;
      let cls = "cal-cell" + weekendClass(weekday);
      if (day === now.getDate()) cls += " today";
      if (marked.has(day)) cls += " marked";
      const cell = el("div", cls);
      cell.appendChild(el("span", "cal-day", String(day)));
      grid.appendChild(cell);
    }
  }

  /** 日曜・土曜に付ける class 名を返す。 */
  function weekendClass(weekday) {
    if (weekday === 0) return " sun";
    if (weekday === 6) return " sat";
    return "";
  }

  // ------------------------------------------------------------------------
  // 予定リスト
  // ------------------------------------------------------------------------

  /** 予定の日付を「10/15（木）」のような文字にする。 */
  function formatDate(ev) {
    const d = parseDateKey(ev.next_date);
    return (d.getMonth() + 1) + "/" + d.getDate() + "（" + WEEKDAYS[d.getDay()] + "）";
  }

  /** 予定の時刻を「13:00〜15:00」のような文字にする。終日なら空文字。 */
  function formatTime(ev) {
    if (!ev.start_time) return "";
    // "09:00" → "9:00" のように先頭の 0 を取って見やすくする
    let text = ev.start_time.replace(/^0/, "") + "〜";
    if (ev.end_time) text += ev.end_time.replace(/^0/, "");
    return text;
  }

  /** 予定のリスト（ul 要素）を描く。空なら「予定はありません」と出す。 */
  function renderEventList(listId, events) {
    const ul = document.getElementById(listId);
    ul.innerHTML = "";

    if (events.length === 0) {
      ul.appendChild(el("li", "event-empty", "予定はありません"));
      return;
    }

    events.forEach(function (ev) {
      // 1件を「日付 | タイトル（時刻） | あと○日」の1行にして、たくさん並べられるようにする
      const li = el("li", "event" + (ev.important ? " important" : ""));

      li.appendChild(el("div", "event-date", formatDate(ev)));

      const title = el("div", "event-title");
      // 重要な予定はタイトルの前に ★ を付けて強調する
      title.appendChild(el("span", "", (ev.important ? "★ " : "") + ev.title));
      const time = formatTime(ev);
      if (time) title.appendChild(el("span", "event-time", time));
      li.appendChild(title);

      // 右端の「あと○日」
      const days = daysUntil(ev.next_date);
      li.appendChild(el("div", "event-days" + (days === 0 ? " is-today" : ""), "あと" + days + "日"));

      ul.appendChild(li);
    });
  }

  /** 受け取ったデータで、カレンダーと予定リストをすべて描き直す。 */
  function render() {
    renderedToday = toDateKey(new Date());
    const data = latestData || { upcoming: [], important: [], marked_days: [] };

    renderMiniCalendar(data.marked_days);
    renderEventList("upcoming-list", data.upcoming);
    renderEventList("important-list", data.important);
    // 重要な予定が中段にすべて入っているときは、下段ごと隠す
    document.getElementById("important-section").hidden = data.important.length === 0;
  }

  // ------------------------------------------------------------------------
  // データの取得と定期更新
  // ------------------------------------------------------------------------

  /**
   * サーバーから最新の予定を取ってきて描き直す。
   * 通信に失敗しても（サーバー再起動中など）、前のデータのまま表示を続けます。
   */
  function refresh() {
    fetch("/api/display", { cache: "no-store" })
      .then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then(function (data) {
        latestData = data;
        render();
      })
      .catch(function (err) {
        console.warn("予定の取得に失敗しました:", err);
      });
  }

  /**
   * 日付が変わったかを確認し、変わっていたらすぐに描き直す。
   * 「あと○日」やカレンダーの「今日」の印を、0:00 を過ぎたらすぐ更新するためです。
   */
  function checkDateChange() {
    if (toDateKey(new Date()) !== renderedToday) {
      render(); // 手元のデータで「あと○日」をすぐ数え直す
      refresh(); // 終わった予定が消えるよう、サーバーからも取り直す
    }
  }

  render(); // まずは空の状態でカレンダーだけ描く
  refresh();
  setInterval(refresh, config.refreshSeconds * 1000);
  setInterval(checkDateChange, 5 * 1000);
})();
