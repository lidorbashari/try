/* Mashup Lab v5 · "מעברי מילים" view + transition player (glue).
   Load order in the built file: app script (defines window.MashApp) → window.WORDPLAY_LINKS = <links.json> → wordplay.js
   → timing.js (window.WordTiming) → this file.
   Uses only the public hooks: MashApp.{E, DATA, pairAny, play, addTab, refresh} and the engine API (SPEC §3).
   "נגן מעבר" plays the transition on the engine's word-play player (E.wordplay): A from a few bars before its word,
   then B on the next beat, stretched to A's tempo and key, so B's word answers A's on the same beat grid. The cut comes
   from WordTiming.plan with the word timestamps measured on GitHub (wordtimes.json) and the song analysis
   (analysis.json); without them it falls back to sung-phrase boundaries, and without decoded audio to the old player. */
(function () {
  "use strict";
  var App = window.MashApp, W = window.Wordplay;
  if (!App || !W || !App.E || !App.DATA) return;
  var E = App.E, DATA = App.DATA;
  var GN = { mizr: "מזרחית", ilpop: "פופ ישראלי", house: "האוס", techhouse: "טק האוס", afrohouse: "אפרו האוס", regg: "רגאטון", latin: "לטיני", hiphop: "היפ הופ", rnb: "R&B", pop: "פופ", afro: "אפרוביטס", amapiano: "אמאפיאנו", dancehall: "דאנסהול", techno: "טכנו", edm: "EDM", dnb: "דראם אנד בייס", ukg: "UK גראז׳" };
  var REL = { same: "אותו סולם", adj: "סולמות שכנים", rel: "מז׳ור ומינור באותו מספר" };
  var curated = [], auto = [];
  try { curated = W.resolve(DATA, window.WORDPLAY_LINKS || []); } catch (e) { curated = []; }
  try { auto = W.autoLinks(DATA, { limit: 120, minConf: "mid" }); } catch (e) { auto = []; }
  var ALL = W.merge(curated, auto);
  var f = { type: "all", compat: false, genre: "all" }, shown = 20, run = null, list = ALL, plans = {};
  var TK = function (t) { return String(t.t) + " | " + String(t.a); };
  function lkey(l) { return TK(DATA[l.ai]) + " || " + TK(DATA[l.bi]); }
  function wordtimes(l) { var w = window.__wordtimes; return w && w[TK(DATA[l.ai]) + " || " + TK(DATA[l.bi])] || null; }
  function analysis(t, h) { var m = window.__analysis && window.__analysis.map, v = m && m[TK(t)]; return v && !v.err && (!h || !v.h || v.h === h) ? v : null; }

  var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); };
  var ic = function (id) { return '<svg class="i" aria-hidden="true"><use href="#i-' + id + '"/></svg>'; };
  function hl(title, phrase) {
    var t = String(title), low = t.toLowerCase(), p = String(phrase || "").replace(/[?!.]+$/, "").trim();
    var cands = p ? [p].concat(p.split(/\s+/).map(function (w) { return w.replace(/[?!.,]/g, ""); }).filter(function (w) { return w.length >= 2; }).sort(function (a, b) { return b.length - a.length; })) : [];
    for (var i = 0; i < cands.length; i++) {
      var k = low.indexOf(cands[i].toLowerCase());
      if (k >= 0) return esc(t.slice(0, k)) + '<mark class="wp-w">' + esc(t.slice(k, k + cands[i].length)) + "</mark>" + esc(t.slice(k + cands[i].length));
    }
    return esc(t);
  }
  function words(l) { var p = String(l.word || "").split(/\s+(?:→|=)\s+/); return { a: p[0], b: p[1] || p[0] }; }
  function hype(n) {
    var s = '<span class="wp-hype" role="img" aria-label="הייפ ' + n + ' מתוך 9">';
    for (var i = 1; i <= 9; i++) s += '<i class="' + (i <= n ? "on" : "") + '"></i>';
    return s + "<b>" + (n >= 8 ? "פיצוץ" : n >= 6 ? "חזק" : "נעים") + "</b></span>";
  }
  function mixLine(m) {
    var t = m.tempoMode && m.tempoMode !== "1:1" ? "יחס קצב 2:1" : (m.tempoDiffPct ? "הפרש קצב " + m.tempoDiffPct + "%" : "אותו קצב");
    var k = m.rel ? REL[m.rel] : "סולמות מתנגשים";
    var en = m.dE >= 1 ? "האנרגיה עולה" : m.dE >= -1 ? "האנרגיה נשמרת" : "האנרגיה יורדת";
    return '<div class="wp-mix">' + (m.compatible ? '<span class="ok">' + ic("check") + "תואם · " + k + " · " + t + "</span>" : '<span class="no">' + k + " · " + t + "</span>") +
      '<span class="tech">' + esc(m.technique_he || m.technique) + "</span><span>" + en + "</span></div>";
  }
  function row(t, side, w) {
    return '<div class="wp-row"><span class="wp-tag ' + side + '">' + (side === "a" ? "A" : "B") + '</span><div class="wp-tx"><bdi class="wp-t">' + hl(t.t, w) + '</bdi><span class="wp-meta"><bdi>' + esc(String(t.a).split(",")[0]) + "</bdi> · " + esc(GN[t.g] || t.g) + "</span></div></div>";
  }
  function cardHTML(l, n) {
    var A = DATA[l.ai], B = DATA[l.bi], w = words(l), live = run && run.link === l;
    return '<article class="wp-card" data-wi="' + n + '" style="--d:' + Math.min(n % 20, 10) * 40 + 'ms">' +
      '<div class="wp-head"><span class="wp-type t-' + esc(l.type) + '">' + esc(l.type_he || l.type) + "</span>" + (l.src === "curated" ? '<span class="wp-src">' + ic("spark") + "נבחר ביד</span>" : '<span class="wp-src">אוטומטי</span>') + hype(l.hype) + "</div>" +
      row(A, "a", w.a) + '<div class="wp-arrow" aria-hidden="true">↓</div>' + row(B, "b", w.b) +
      (l.why_he ? '<p class="why">' + ic("spark") + "<span>" + esc(l.why_he) + "</span></p>" : "") +
      '<ol class="wp-plan"><li><b class="a">A</b><span>' + esc(l.cueA && l.cueA.he) + '</span></li><li><b class="b">B</b><span>' + esc(l.cueB && l.cueB.he) + "</span></li></ol>" +
      mixLine(l.mix) + (live && run.live ? liveHTML(run) : plans[lkey(l)] ? howHTML(plans[lkey(l)]) : '<p class="wp-note">' + esc(l.note_he || "הערכה לפי מבנה טיפוסי של הסגנון: לבדוק באוזן") + "</p>") +
      '<div class="c-acts"><button class="btn pri" type="button" data-wact="play" aria-pressed="' + !!live + '">' + ic(live ? "pause" : "play") + "<span>" + (live ? "עצור מעבר" : "נגן מעבר") + '</span></button><button class="btn n" type="button" data-wact="mixer">' + ic("sliders") + "<span>פתח במיקסר</span></button></div></article>";
  }

  function howHTML(pl) {
    var s = (pl.summary || []).concat(pl.notes || []);
    return s.length ? '<ul class="wp-how">' + s.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + "</ul>" : "";
  }
  function liveHTML(r) {
    return '<div class="wp-live" aria-live="polite"><div class="wp-bar" aria-hidden="true"><i class="fill"></i><b class="cutm"></b></div>' +
      '<p class="wp-now">' + esc(r && r.msg || "מכין את המעבר: מפענח את שני הקטעים ומתאים קצב וסולם…") + "</p>" + (r && r.plan ? howHTML(r.plan) : "") + "</div>";
  }

  /* ---------- view ---------- */
  var view = document.createElement("section");
  view.className = "wp";
  var types = ["all"].concat(["chain", "answer", "lang", "same", "count", "theme"].filter(function (t) { return ALL.some(function (l) { return l.type === t; }); }));
  var gset = {}; ALL.forEach(function (l) { gset[DATA[l.ai].g] = 1; gset[DATA[l.bi].g] = 1; });
  view.innerHTML =
    '<header class="lt"><div class="lt-t"><p class="eyebrow"><svg class="logo" viewBox="0 0 22 14" aria-hidden="true"><circle class="la" cx="7" cy="7" r="6.5"/><circle class="lb" cx="15" cy="7" r="6.5"/></svg>מעבדת המשאפים</p><h1>מעברי מילים</h1></div>' +
    '<button class="hbtn glass" type="button" data-act="source" aria-label="מאיפה מגיע השמע">' + ic("wave") + "</button></header>" +
    '<p class="sec-sub wp-sub" style="margin-top:-12px"></p>' +
    '<p class="wp-help">ההוק של שיר A נוחת על מילה, ושיר B נכנס וממשיך או עונה לה. "נגן מעבר" מנגן את A כמה תיבות לפני המילה, ובפעמה שמיד אחריה B נכנס כשהוא מותאם לקצב ולסולם של A, כך שהמילה שלו עונה על אותו ביט. מתחת לכפתור כתוב מה בדיוק נעשה (קצב, סולם, איפה החיתוך), כדי שתוכל לעשות את אותו הדבר על הדקים שלך. ההדגמה מתנגנת מקטעי התצוגה המקדימה של 30 שניות.</p>' +
    '<div class="wp-filters"><div class="chips" role="group" aria-label="סוג מעבר">' + types.map(function (t) { return '<button class="chip" type="button" data-wf="type" data-v="' + t + '" aria-pressed="' + (t === "all") + '">' + (t === "all" ? "הכל" : esc(W.TYPE_HE[t])) + "</button>"; }).join("") + "</div>" +
    '<div class="wp-frow"><button class="tchip" type="button" data-wf="compat" aria-pressed="false">' + ic("check") + 'רק תואמים בסולם ובקצב</button><select class="wp-sel" data-wf="genre" aria-label="סגנון"><option value="all">כל הסגנונות</option>' +
    Object.keys(GN).filter(function (g) { return gset[g]; }).map(function (g) { return '<option value="' + g + '">' + esc(GN[g]) + "</option>"; }).join("") + "</select></div></div>" +
    '<div class="wp-list"></div><button class="btn n wp-more" type="button" data-wact="more" hidden>להציג עוד</button>';
  var $l = view.querySelector(".wp-list"), $more = view.querySelector(".wp-more"), $sub = view.querySelector(".wp-sub");

  function filtered() {
    return ALL.filter(function (l) {
      if (f.type !== "all" && l.type !== f.type) return false;
      if (f.compat && !l.mix.compatible) return false;
      if (f.genre !== "all" && DATA[l.ai].g !== f.genre && DATA[l.bi].g !== f.genre) return false;
      return true;
    });
  }
  function render() {
    list = filtered();
    var nc = list.filter(function (l) { return l.src === "curated"; }).length;
    $sub.textContent = list.length + " מעברים · " + nc + " נבחרו ביד";
    $l.innerHTML = list.length ? list.slice(0, shown).map(cardHTML).join("") : '<p class="wp-help">אין מעברים שמתאימים לסינון הזה. אפשר לבטל את "רק תואמים" או לבחור סגנון אחר.</p>';
    $more.hidden = list.length <= shown;
  }
  function paint(btn, on) {
    if (!btn) return;
    btn.setAttribute("aria-pressed", String(!!on));
    btn.innerHTML = ic(on ? "pause" : "play") + "<span>" + (on ? "עצור מעבר" : "נגן מעבר") + "</span>";
  }

  /* ---------- transition player ---------- */
  function stopRun() {
    if (!run) return;
    clearInterval(run.iv); clearTimeout(run.to); if (run.raf) cancelAnimationFrame(run.raf);
    var r = run, b = run.btn; run = null; paint(b, false);
    if (r.live) { var c = cardOf(r), box = c && c.querySelector(".wp-live"); if (box) { var tmp = document.createElement("div"); tmp.innerHTML = r.plan ? howHTML(r.plan) : ""; if (tmp.firstChild) box.replaceWith(tmp.firstChild); else box.remove(); } }
  }
  function ramp(r, ms, done) {
    var t0 = performance.now();
    (function step(now) {
      if (run !== r) return;
      var x = Math.min(1, Math.max(0, (now - t0) / Math.max(1, ms)));
      E.setCrossfader(x);
      if (x < 1) r.raf = requestAnimationFrame(step); else if (done) done();
    })(t0);
  }
  function later(r, ms, fn) { r.to = setTimeout(function () { if (run === r) fn(); }, ms); }
  function fire(r) {
    r.fired = true;
    if (E.holdClean) E.holdClean(12000);   /* a word handoff needs both full mixes, no vocal clean-up during the overlap */
    var pl = r.plan;
    if (pl.style === "spinback") {            /* stop-and-drop: A out on the word, B lands one beat later on the 1 */
      E.setCrossfader(1);
      later(r, Math.round(pl.beat * 1000), function () { E.play("B"); later(r, 400, function () { E.pause("A"); }); });
      return;
    }
    E.play("B");
    if (pl.style === "cut") { E.setCrossfader(1); later(r, 300, function () { E.pause("A"); }); return; }
    /* blend: 2-bar crossfader ride; echo: a one-beat fall-away like an echo tail */
    ramp(r, pl.xfMs, function () { later(r, pl.style === "echo" ? Math.round(pl.bar * 1000) : 200, function () { E.pause("A"); }); });
  }
  function tick(r) {
    if (run !== r) return;
    var st = E.state(), a = st.A || {}, b = st.B || {};
    if (!r.fired) {
      if (a.busy || a.buffering || !a.playing) {
        if (r.p0 != null && !a.playing && !a.busy && !a.buffering) stopRun();          /* paused from elsewhere */
        else if (r.p0 == null && Date.now() - r.start > 9000) stopRun();               /* never started */
        return;
      }
      if (r.p0 == null) { r.p0 = a.pos; return; }
      if (a.pos - r.p0 >= r.plan.T * (r.plan.rates.A || 1) - 0.02) fire(r);             /* pos is track time; T is real time at the synced rate */
    } else if (!a.playing && !b.playing && !b.busy && !b.buffering) stopRun();
  }
  function cardOf(r) { var c = r && r.btn && r.btn.closest(".wp-card"); return c && view.contains(c) ? c : r && view.querySelector('.wp-card[data-wi="' + r.wi + '"]'); }
  function paintLive(r) {
    var c = cardOf(r); if (!c) return;
    var box = c.querySelector(".wp-live");
    if (!box) { var note = c.querySelector(".wp-note, .wp-how"); var tmp = document.createElement("div"); tmp.innerHTML = liveHTML(r); box = tmp.firstChild; if (note) note.replaceWith(box); else c.querySelector(".c-acts").before(box); }
    var st = r.st || {}, fill = box.querySelector(".fill"), cm = box.querySelector(".cutm"), now = box.querySelector(".wp-now");
    if (st.total > 0) { fill.style.width = Math.min(100, st.t / st.total * 100).toFixed(1) + "%"; cm.style.insetInlineStart = (st.cut / st.total * 100).toFixed(1) + "%"; cm.hidden = false; } else { fill.style.width = "0"; cm.hidden = true; }
    if (now.textContent !== r.msg) now.textContent = r.msg || "";
    if (r.plan && !box.querySelector(".wp-how")) box.insertAdjacentHTML("beforeend", howHTML(r.plan));
  }
  function liveTick(r) {
    if (run !== r) return;
    var st = r.st = E.wpState ? E.wpState() : { phase: "idle" }, pl = r.plan;
    if (st.phase === "idle" || st.phase === "done") { if (r.started) { stopRun(); if (App.refresh) App.refresh(); } return; }
    if (st.phase === "load" || !pl) r.msg = "מכין את המעבר: מפענח את שני הקטעים ומתאים קצב וסולם…";
    else if (st.phase === "a") {
      var toWord = (pl.wA[0] - pl.aStart) - st.t, toCut = st.cut - st.t;
      r.msg = toWord > .25 ? "A מתנגן · המילה " + (pl.foundA ? "של A" : "(סוף המשפט)") + " בעוד " + Math.ceil(toWord) + " שנ׳" : toCut > 0 ? "המילה של A… ו־B נכנס על הביט" : "";
    } else r.msg = pl.drop ? "הדרופ של B! ממשיכים עם B" : "B ענה על הביט · ממשיכים עם B";
    paintLive(r);
  }
  function playTransition(l, btn) {
    E.gesture();                                   /* first, synchronously (iOS) */
    if (run && run.link === l) { if (E.wpStop) E.wpStop(); E.pauseAll(); stopRun(); if (App.refresh) App.refresh(); return; }
    stopRun();
    if (!E.wordplay || !window.WordTiming) { legacyPlay(l, btn); return; }
    var A = DATA[l.ai], B = DATA[l.bi], wi = +(btn.closest(".wp-card") || {}).dataset.wi;
    var r = run = { link: l, btn: btn, wi: wi, start: Date.now(), plan: null, msg: "מכין את המעבר: מפענח את שני הקטעים ומתאים קצב וסולם…", started: false, live: true };
    paint(btn, true); paintLive(r);
    r.iv = setInterval(function () { liveTick(r); }, 120);
    E.wordplay({ a: A, b: B, plan: function (info) { return planFor(l, info); } }).then(function (pl) {
      if (run !== r || !pl) return;
      r.plan = plans[lkey(l)] = pl; r.started = true; liveTick(r);
    }, function () {
      if (run !== r) return;
      clearInterval(r.iv); run = null; legacyPlay(l, btn);           /* no decoded audio here: the streamed player */
    });
    if (App.refresh) App.refresh();
  }
  /* the plan of a link for the previews as loaded (word times and analysis only when measured on these exact previews) */
  function planFor(l, info) {
    var A = DATA[l.ai], B = DATA[l.bi], wt = wordtimes(l), w2 = wt ? { a: wt.a_h && wt.a_h !== info.hA ? null : wt.a, b: wt.b_h && wt.b_h !== info.hB ? null : wt.b } : {};
    return window.WordTiming.plan(l, info, { wt: w2, anA: analysis(A, info.hA), anB: analysis(B, info.hB) });
  }
  function legacyPlay(l, btn) {
    var A = DATA[l.ai], B = DATA[l.bi], plan = W.previewPlan(l, DATA);
    App.play(App.pairAny(A, B), null, { sync: plan.sync });     /* load only: A → deck A, B → deck B (halts both) */
    E.setCrossfader(0);
    E.playOnly("A");
    var r = run = { link: l, btn: btn, plan: plan, p0: null, fired: false, start: Date.now() };
    paint(btn, true);
    r.iv = setInterval(function () { tick(r); }, 40);
    if (App.refresh) App.refresh();
  }
  function openInMixer(l, btn) {
    E.gesture(); if (E.wpStop) E.wpStop(); stopRun();
    var plan = W.previewPlan(l, DATA), pl = plans[lkey(l)];
    App.play(App.pairAny(DATA[l.ai], DATA[l.bi]), null, { sync: pl ? pl.synced : plan.sync, mixer: true, opener: btn });
    if (pl) setTimeout(function () { E.seek("A", pl.aStart); E.seek("B", Math.max(0, pl.bPos - (pl.pre || 0) * pl.r)); }, 60);  /* cued where the transition starts */
  }

  view.addEventListener("click", function (ev) {
    var t = ev.target.closest("[data-wact],[data-wf]"); if (!t || !view.contains(t)) return;
    var act = t.dataset.wact, wf = t.dataset.wf;
    if (act === "more") { shown += 20; render(); return; }
    if (act) { var card = t.closest(".wp-card"), l = card && list[+card.dataset.wi]; if (!l) return; if (act === "play") playTransition(l, t); else if (act === "mixer") openInMixer(l, t); return; }
    if (wf === "type") { f.type = t.dataset.v; view.querySelectorAll('[data-wf="type"]').forEach(function (b) { b.setAttribute("aria-pressed", String(b === t)); }); }
    else if (wf === "compat") { f.compat = !f.compat; t.setAttribute("aria-pressed", String(f.compat)); }
    else return;
    shown = 20; render();
  });
  view.addEventListener("change", function (ev) { if (ev.target.dataset.wf === "genre") { f.genre = ev.target.value; shown = 20; render(); } });

  var css = document.createElement("style");
  css.textContent =
    ".wp-help{font-size:14px;line-height:20px;color:var(--label-2);margin:0 0 14px}.wp-filters{display:grid;gap:10px;margin-bottom:14px;min-width:0}" +
    ".wp .chips{display:flex;gap:8px;overflow-x:auto;scrollbar-width:none;padding-bottom:2px}.wp .chips::-webkit-scrollbar{display:none}.wp .chip[aria-pressed=true]{background:var(--accent);color:#fff}" +
    ".wp-frow{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.wp-sel{height:36px;border-radius:18px;border:0;background:var(--card-hi);color:var(--label);padding:0 12px;font:inherit;font-size:14px;max-width:100%}" +
    ".wp-list{display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(min(100%,340px),1fr))}" +
    ".wp-card{position:relative;background:var(--card);border-radius:24px;padding:14px;display:grid;gap:10px;min-width:0}" +
    ".wp-head{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.wp-type{font-size:12px;font-weight:700;padding:3px 9px;border-radius:10px;background:var(--accent-tint);color:var(--accent-ink)}" +
    ".wp-type.t-answer{background:var(--beat-tint);color:var(--beat-ink)}.wp-type.t-lang{background:var(--violet-tint);color:var(--violet-ink)}.wp-type.t-same,.wp-type.t-count{background:var(--ok-tint);color:var(--ok-ink)}.wp-type.t-theme{background:var(--fill);color:var(--label-2)}" +
    ".wp-src{display:inline-flex;align-items:center;gap:4px;font-size:12px;color:var(--label-2)}.wp-src .i{width:12px;height:12px}" +
    ".wp-hype{margin-inline-start:auto;display:inline-flex;align-items:center;gap:2px}.wp-hype i{width:5px;height:14px;border-radius:3px;background:var(--fill)}.wp-hype i.on{background:linear-gradient(var(--vocal),var(--accent))}.wp-hype b{font-size:12px;margin-inline-start:6px;color:var(--label-2)}" +
    ".wp-row{display:flex;gap:10px;align-items:center;min-width:0}.wp-tx{min-width:0}.wp-tag{flex:none;width:26px;height:26px;border-radius:13px;display:grid;place-items:center;font-size:12px;font-weight:800;color:#fff;background:var(--vocal)}.wp-tag.b{background:var(--beat)}" +
    ".wp-t{display:block;font-size:17px;font-weight:700;line-height:22px;overflow-wrap:anywhere}.wp-meta{display:block;font-size:13px;color:var(--label-2)}.wp-arrow{margin:-6px 0 -6px 8px;color:var(--label-2);font-size:13px}" +
    ".wp-w{background:none;color:var(--accent-ink);font-weight:800;text-decoration:underline;text-decoration-thickness:2px;text-underline-offset:3px}" +
    ".wp-plan{margin:0;padding:0;list-style:none;display:grid;gap:6px;font-size:14px;line-height:19px}.wp-plan li{display:flex;gap:8px}.wp-plan b{flex:none;font-size:11px;width:20px;height:20px;border-radius:10px;display:grid;place-items:center;color:#fff;background:var(--vocal)}.wp-plan b.b{background:var(--beat)}" +
    ".wp-mix{display:flex;flex-wrap:wrap;gap:6px;font-size:12px}.wp-mix span{display:inline-flex;align-items:center;gap:4px;padding:3px 8px;border-radius:9px;background:var(--fill)}.wp-mix .i{width:12px;height:12px}.wp-mix .ok{background:var(--good-tint);color:var(--good-ink)}.wp-mix .tech{background:var(--warn-tint);color:var(--warn-ink)}" +
    ".wp-live{display:grid;gap:8px}.wp-bar{position:relative;height:8px;border-radius:4px;background:var(--fill);overflow:hidden}" +
    ".wp-bar .fill{position:absolute;inset-block:0;inset-inline-start:0;width:0;background:linear-gradient(90deg,var(--vocal),var(--beat));border-radius:4px;transition:width .12s linear}" +
    ".wp-bar .cutm{position:absolute;inset-block:-2px;width:3px;margin-inline-start:-1px;background:var(--label);border-radius:2px}" +
    ".wp-now{margin:0;font-size:14px;font-weight:600;color:var(--label);min-height:20px}" +
    ".wp-how{margin:0;padding:0 18px 0 0;display:grid;gap:4px;font-size:13px;line-height:18px;color:var(--label-2)}" +
    ".wp-note{margin:0;font-size:12px;color:var(--label-2)}.wp-card .btn.pri[aria-pressed=true]{background:var(--accent);color:#fff}.wp-more{margin:14px auto 0;display:flex}" +
    "@media (prefers-reduced-motion:no-preference){.wp-card{animation:wpIn .5s cubic-bezier(.3,1.35,.45,1) both;animation-delay:var(--d,0ms)}@keyframes wpIn{from{opacity:0;transform:translateY(14px);filter:blur(10px)}}}";
  document.head.appendChild(css);

  App.addTab({
    id: "words", label: "מעברים", view: view, onShow: render,
    svg: '<svg class="i" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 5.5h11a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2H9l-4 3.5v-3.5H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2z"/><path d="M17 9.5h3a2 2 0 0 1 2 2v4.5a2 2 0 0 1-2 2h-1v3l-3.5-3H12"/></svg>'
  });
  render();
  window.WordplayUI = { links: ALL, curated: curated.length, auto: auto.length, render: render, play: playTransition, stop: stopRun, filter: f, planFor: planFor, key: lkey };
})();
