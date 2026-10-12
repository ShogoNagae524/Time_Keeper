/*
 * clock.js — アナログ時計と時限表示（モニター画面用）
 *
 * 【このファイルの役割】
 *   - 文字盤（目盛りと 1〜12 の数字）を SVG で描く
 *   - 時針・分針を、いまの時刻に合わせて滑らかに回す（秒針はなし）
 *   - 文字盤の中に「いまの時限」（1限・休憩時間・no schedule など）を表示する
 *   - 時計の下に日付と曜日を表示する
 *
 * 時限の時刻は config.py の PERIODS で設定し、display.html 経由で
 * window.APP_CONFIG.periods として受け取ります。
 */

(function () {
  "use strict";

  const SVG_NS = "http://www.w3.org/2000/svg";
  const WEEKDAYS = ["日", "月", "火", "水", "木", "金", "土"];
  const config = window.APP_CONFIG;

  /**
   * "9:00" のような時刻の文字列を「0時からの秒数」に変換する。
   * 時限の判定を数値の大小比較だけでできるようにするためです。
   */
  function timeTextToSeconds(text) {
    const [h, m] = text.split(":").map(Number);
    return h * 3600 + m * 60;
  }

  // 時限の設定を、比較しやすい秒数に変換しておく（起動時に1回だけ）
  const periods = config.periods.map(function (p) {
    return {
      start: timeTextToSeconds(p.start),
      end: timeTextToSeconds(p.end),
      label: p.label,
    };
  });

  /**
   * 文字盤（60本の目盛りと 1〜12 の数字）を描く。最初に1回だけ呼ぶ。
   * 5分ごと（= 数字の位置）の目盛りは太く長くして見やすくしています。
   */
  function drawDial() {
    const ticks = document.getElementById("clock-ticks");
    const numbers = document.getElementById("clock-numbers");

    for (let i = 0; i < 60; i++) {
      const isHour = i % 5 === 0;
      const line = document.createElementNS(SVG_NS, "line");
      line.setAttribute("x1", 0);
      line.setAttribute("y1", -92);
      line.setAttribute("x2", 0);
      line.setAttribute("y2", isHour ? -83 : -88);
      line.setAttribute("class", isHour ? "tick tick-hour" : "tick");
      // 12時の位置に描いた線を、i × 6度 回して並べる
      line.setAttribute("transform", "rotate(" + i * 6 + ")");
      ticks.appendChild(line);
    }

    for (let n = 1; n <= 12; n++) {
      // 12時を 0度として時計回りに 30度ずつ。sin/cos で座標を求める
      const angle = (n * 30 * Math.PI) / 180;
      const r = 71; // 中心から数字までの距離
      const text = document.createElementNS(SVG_NS, "text");
      text.setAttribute("x", (Math.sin(angle) * r).toFixed(2));
      text.setAttribute("y", (-Math.cos(angle) * r).toFixed(2));
      text.setAttribute("class", "clock-number");
      text.textContent = n;
      numbers.appendChild(text);
    }
  }

  /**
   * いまの時刻（0時からの秒数）から、表示する時限の文字を返す。
   * 「開始 <= いま < 終了」で判定するので、終了時刻ちょうどで次の表示に切り替わります。
   * 曜日は見ないので、土日・祝日も同じ表示になります。
   */
  function currentPeriodLabel(secondsOfDay) {
    for (const p of periods) {
      if (p.start <= secondsOfDay && secondsOfDay < p.end) {
        return p.label;
      }
    }
    return config.noPeriodLabel;
  }

  const hourHand = document.getElementById("hand-hour");
  const minuteHand = document.getElementById("hand-minute");
  const periodText = document.getElementById("clock-period");
  const dateText = document.getElementById("clock-date");

  // 前回表示した文字を覚えておき、変わったときだけ書き換える（無駄な描き直しを防ぐ）
  let lastPeriod = null;
  let lastDate = null;

  /**
   * 針・時限・日付を、いまの時刻に合わせて更新する。
   * requestAnimationFrame で画面の描き換えごとに呼ばれるので、針が滑らかに動きます。
   */
  function update() {
    const now = new Date();
    const h = now.getHours();
    const m = now.getMinutes();
    // 秒とミリ秒まで含めた「分」。これを使うことで分針がカクカクせず滑らかに動く
    const minutes = m + now.getSeconds() / 60 + now.getMilliseconds() / 60000;

    // 分針：1分で 6度（60分で 360度）
    minuteHand.setAttribute("transform", "rotate(" + minutes * 6 + ")");
    // 時針：1時間で 30度（12時間で 360度）。分の分だけ少しずつ進める
    hourHand.setAttribute("transform", "rotate(" + ((h % 12) + minutes / 60) * 30 + ")");

    const secondsOfDay = h * 3600 + m * 60 + now.getSeconds();
    const period = currentPeriodLabel(secondsOfDay);
    if (period !== lastPeriod) {
      periodText.textContent = period;
      lastPeriod = period;
    }

    const dateLabel =
      now.getFullYear() + "年" + (now.getMonth() + 1) + "月" + now.getDate() + "日（" +
      WEEKDAYS[now.getDay()] + "）";
    if (dateLabel !== lastDate) {
      dateText.textContent = dateLabel;
      lastDate = dateLabel;
    }

    requestAnimationFrame(update);
  }

  drawDial();
  update();
})();
