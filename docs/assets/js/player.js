/* DJ Lab — global player bar, inline mini players, track cards, track drawer, energy chart. */
(function () {
  'use strict';
  var DJ = window.DJ, doc = document, I = DJ.icon, esc = DJ.esc;

  /* =====================================================================================
     Player (single HTMLAudioElement for the whole page)
     ===================================================================================== */
  var audio = new Audio();
  audio.preload = 'metadata';
  var cur = null, queue = [], qi = -1, bar = null, wave = null, listeners = [], raf = 0;
  var vol = DJ.store.get('vol', 0.9);
  audio.volume = vol;

  function emit(kind) { for (var i = 0; i < listeners.length; i++) { try { listeners[i](kind, api); } catch (e) { console.error(e); } } }
  function loop() {
    raf = 0;
    if (!audio.paused) { tick(); raf = requestAnimationFrame(loop); }
  }
  function tick() {
    if (!bar || !cur) return;
    var d = duration();
    if (wave) wave.set(d ? audio.currentTime / d : 0);
    bar.cur.textContent = DJ.fmtTime(audio.currentTime);
    bar.canvas.setAttribute('aria-valuenow', Math.round(audio.currentTime));
    bar.canvas.setAttribute('aria-valuetext', DJ.fmtTime(audio.currentTime) + ' מתוך ' + DJ.fmtTime(d));
    emit('tick');
  }
  function duration() { return (isFinite(audio.duration) && audio.duration) || (cur && cur.duration_sec) || 0; }

  function buildBar() {
    if (bar) return bar;
    var el = DJ.h(
      '<div class="player" role="region" aria-label="נגן מוזיקה">' +
      '<div class="container-wide player-inner">' +
      '<div class="pl-track"><div class="pl-art"></div><div class="pl-text"><button class="pl-title" type="button" data-pl-open></button><div class="pl-sub"></div></div></div>' +
      '<div class="pl-controls"><button class="icon-btn pl-prev" type="button" aria-label="הטראק הקודם">' + I('prev') + '</button>' +
      '<button class="pl-play" type="button" aria-label="ניגון">' + I('play') + '</button>' +
      '<button class="icon-btn pl-next" type="button" aria-label="הטראק הבא">' + I('next') + '</button></div>' +
      '<div class="pl-wave"><span class="pl-time" data-cur>0:00</span><div class="pl-canvas-wrap"><canvas role="slider" tabindex="0" aria-label="מיקום בטראק (חצים להזזה)" aria-valuemin="0"></canvas><div class="pl-cues"></div></div><span class="pl-time" data-dur>0:00</span></div>' +
      '<div class="pl-actions"><label class="pl-vol" title="עוצמה">' + I('volume') + '<span class="sr-only">עוצמה</span><input type="range" min="0" max="1" step="0.01"></label>' +
      '<button class="icon-btn pl-compat" type="button" aria-label="מה מתאים למיקס" title="מה מתאים למיקס">' + I('wand') + '</button>' +
      '<a class="icon-btn pl-dl" download aria-label="הורדת MP3" title="הורדת MP3">' + I('download') + '</a>' +
      '<button class="icon-btn pl-close" type="button" aria-label="סגירת הנגן" title="סגירה">' + I('close') + '</button></div>' +
      '</div></div>');
    doc.body.appendChild(el);
    bar = {
      el: el, art: el.querySelector('.pl-art'), title: el.querySelector('.pl-title'), sub: el.querySelector('.pl-sub'),
      play: el.querySelector('.pl-play'), prev: el.querySelector('.pl-prev'), next: el.querySelector('.pl-next'),
      canvas: el.querySelector('canvas'), cues: el.querySelector('.pl-cues'), cur: el.querySelector('[data-cur]'), dur: el.querySelector('[data-dur]'),
      vol: el.querySelector('.pl-vol input'), dl: el.querySelector('.pl-dl'), close: el.querySelector('.pl-close'), compat: el.querySelector('.pl-compat')
    };
    bar.vol.value = vol;
    bar.vol.addEventListener('input', function () { audio.volume = +bar.vol.value; DJ.store.set('vol', audio.volume); });
    bar.play.addEventListener('click', function () { api.toggle(); });
    bar.prev.addEventListener('click', function () { api.prev(); });
    bar.next.addEventListener('click', function () { api.next(); });
    bar.close.addEventListener('click', function () { api.stop(); });
    bar.title.addEventListener('click', function () { if (cur) DJ.openTrack(cur.id); });
    bar.compat.addEventListener('click', function () { if (cur) DJ.openTrack(cur.id, { focus: 'compat' }); });
    wave = new DJ.Wave(bar.canvas, {
      onSeek: function (f) { var d = duration(); if (d) { audio.currentTime = f * d; tick(); } },
      onKey: function (k) {
        var d = duration();
        if (k === 'ArrowRight') audio.currentTime = Math.min(d, audio.currentTime + 5);
        if (k === 'ArrowLeft') audio.currentTime = Math.max(0, audio.currentTime - 5);
        if (k === 'Home') audio.currentTime = 0;
        if (k === 'End') audio.currentTime = Math.max(0, d - 1);
        tick();
      }
    });
    return bar;
  }

  function renderBar() {
    buildBar();
    var t = cur;
    bar.el.classList.add('is-visible');
    doc.body.classList.add('has-player');
    bar.art.innerHTML = DJ.coverHTML(t);
    bar.title.textContent = t.title || t.id;
    var isTrack = t.kind === 'track' || (!t.kind && t.genre);
    bar.title.disabled = !isTrack;
    bar.compat.hidden = !isTrack;
    var cam = DJ.camOf(t);
    bar.sub.innerHTML = (t.title_he ? '<span>' + esc(t.title_he) + '</span>' : '') +
      (t.bpm ? '<span dir="ltr">' + DJ.fmtBpm(t.bpm) + ' BPM</span>' : '') + (cam ? DJ.camBadge(cam) : '');
    bar.dl.href = DJ.media(t.file);
    bar.dl.setAttribute('download', (t.file || '').split('/').pop());
    var d = t.duration_sec || 0;
    bar.dur.textContent = DJ.fmtTime(d);
    bar.canvas.setAttribute('aria-valuemax', Math.round(d));
    wave.o.peaks = DJ.peaks(t.file); wave.o.seed = (t.id || '').length;
    wave.w = 0; wave.p = 0; wave.resize();
    // cue markers
    bar.cues.innerHTML = '';
    (t.cues || []).forEach(function (c) {
      if (!d || c.sec == null) return;
      var b = DJ.h('<button type="button" class="pl-cue" style="left:' + (100 * c.sec / d).toFixed(3) + '%;--c:' + esc(c.color || DJ.CUE_COLORS[c.slot] || '#fff') + '" title="Hot Cue ' + esc(c.slot) + ' · ' + esc(c.name || '') + ' · ' + DJ.fmtTime(c.sec) + '" aria-label="קפיצה ל-Hot Cue ' + esc(c.slot) + ' ' + esc(c.name || '') + '">' + esc(c.slot) + '</button>');
      b.addEventListener('click', function () { audio.currentTime = c.sec; if (audio.paused) api.resume(); tick(); });
      bar.cues.appendChild(b);
    });
    bar.prev.disabled = qi <= 0 && audio.currentTime < 3;
    bar.next.disabled = qi < 0 || qi >= queue.length - 1;
    syncPlayBtn();
  }
  function syncPlayBtn() {
    if (!bar) return;
    var p = !audio.paused;
    bar.play.innerHTML = I(p ? 'pause' : 'play');
    bar.play.setAttribute('aria-label', p ? 'השהיה' : 'ניגון');
  }

  audio.addEventListener('play', function () { syncPlayBtn(); if (!raf) raf = requestAnimationFrame(loop); emit('state'); });
  audio.addEventListener('pause', function () { syncPlayBtn(); tick(); emit('state'); });
  audio.addEventListener('loadedmetadata', function () { if (bar) { bar.dur.textContent = DJ.fmtTime(duration()); bar.canvas.setAttribute('aria-valuemax', Math.round(duration())); } });
  audio.addEventListener('ended', function () { if (qi >= 0 && qi < queue.length - 1) api.next(); else { emit('state'); } });
  audio.addEventListener('error', function () {
    if (!cur) return;
    DJ.toast(DJ.isFile ? 'הדפדפן חסם את הקובץ. הריצו שרת מקומי: python -m http.server מתיקיית הריפו.' : 'לא הצלחנו לנגן את הקובץ (אולי הוא עוד לא קיים).');
    emit('state');
  });

  var api = DJ.player = {
    audio: audio,
    get current() { return cur; },
    isCurrent: function (file) { return !!(cur && file && cur.file === file); },
    isPlaying: function (file) { return api.isCurrent(file) && !audio.paused; },
    play: function (item, opts) {
      opts = opts || {};
      if (!item || !item.file) return;
      if (cur && cur.file === item.file && opts.startAt == null) { api.toggle(); return; }
      if (item.has_audio === false) { DJ.toast('הקובץ הזה עדיין ברינדור — בקרוב!'); return; }
      cur = item;
      queue = (opts.queue || [item]).filter(DJ.playable);
      qi = queue.indexOf(item);
      if (qi < 0) { queue = [item]; qi = 0; }
      audio.src = DJ.media(item.file);
      var start = opts.startAt || 0;
      if (start) {
        var seekOnce = function () { audio.currentTime = start; audio.removeEventListener('loadedmetadata', seekOnce); };
        audio.addEventListener('loadedmetadata', seekOnce);
      }
      renderBar();
      var pr = audio.play();
      if (pr && pr.catch) pr.catch(function (e) { if (e && e.name !== 'AbortError') console.warn(e); });
      emit('load');
    },
    resume: function () { var p = audio.play(); if (p && p.catch) p.catch(function () { }); },
    pause: function () { audio.pause(); },
    toggle: function () { if (!cur) return; if (audio.paused) api.resume(); else audio.pause(); },
    seek: function (sec) { if (!cur) return; audio.currentTime = sec; tick(); },
    next: function () { if (qi < queue.length - 1) api.play(queue[qi + 1], { queue: queue, startAt: 0 }); },
    prev: function () {
      if (audio.currentTime > 3 || qi <= 0) { audio.currentTime = 0; tick(); return; }
      api.play(queue[qi - 1], { queue: queue, startAt: 0 });
    },
    stop: function () {
      audio.pause(); cur = null; queue = []; qi = -1;
      if (bar) bar.el.classList.remove('is-visible');
      doc.body.classList.remove('has-player');
      emit('state');
    },
    on: function (fn) { listeners.push(fn); },
    time: function () { return audio.currentTime; },
    duration: duration
  };

  // space toggles the player when nothing interactive is focused
  doc.addEventListener('keydown', function (e) {
    if (e.code !== 'Space' || !cur || DJ.noGlobalSpace) return;
    var t = e.target, tag = t && t.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || tag === 'BUTTON' || tag === 'A' || (t && t.isContentEditable)) return;
    e.preventDefault(); api.toggle();
  });
  doc.addEventListener('djlab:theme', function () { if (wave) { wave.w = 0; wave.resize(); } DJ.$$('.mp-wave canvas').forEach(function (c) { if (c._wave) { c._wave.w = 0; c._wave.resize(); } }); });

  /* =====================================================================================
     Track cards
     ===================================================================================== */
  DJ.trackCard = function (t, opts) {
    opts = opts || {};
    var cam = DJ.camOf(t), playable = DJ.playable(t);
    var el = DJ.h(
      '<article class="track-card' + (playable ? '' : ' is-soon') + '" data-id="' + esc(t.id) + '" style="--cam:' + DJ.cam.color(cam) + '">' +
      '<div class="tc-art">' + DJ.coverHTML(t) +
      (cam ? '<span class="tc-cam">' + DJ.camBadge(cam) + '</span>' : '') +
      (t.bpm ? '<span class="tc-bpm">' + DJ.fmtBpm(t.bpm) + ' BPM</span>' : '') +
      '<button class="tc-play" type="button" ' + (playable ? '' : 'disabled ') + 'aria-label="' + (playable ? 'ניגון ' : 'בקרוב: ') + esc(t.title) + '">' + I('play') + '</button></div>' +
      '<div class="tc-body">' +
      '<button class="tc-title" type="button" title="פרטים ו-Hot Cues">' + esc(t.title || t.id) + '</button>' +
      '<span class="tc-he">' + esc(t.title_he || '') + '</span>' +
      '<div class="tc-meta"><span class="tc-genre">' + esc(t.genre || '') + '</span>' + (playable ? DJ.roleHTML(t.role) : '<span class="badge badge--soon">בקרוב</span>') + DJ.energyHTML(t.energy) + '</div>' +
      '<div class="tc-list-extra"><span class="num muted small" dir="ltr">' + DJ.fmtBpm(t.bpm) + ' BPM</span>' + (cam ? DJ.camBadge(cam) : '') + '<span class="num muted small">' + (t.duration_sec ? DJ.fmtTime(t.duration_sec) : '') + '</span></div>' +
      '</div></article>');
    var playBtn = el.querySelector('.tc-play');
    playBtn.addEventListener('click', function () { DJ.player.play(t, { queue: opts.queue ? opts.queue() : [t] }); });
    el.querySelector('.tc-title').addEventListener('click', function () { DJ.openTrack(t.id); });
    el._sync = function () {
      var on = DJ.player.isPlaying(t.file);
      el.classList.toggle('is-playing', DJ.player.isCurrent(t.file));
      playBtn.innerHTML = I(on ? 'pause' : 'play');
      playBtn.setAttribute('aria-label', (on ? 'השהיה ' : 'ניגון ') + (t.title || ''));
    };
    return el;
  };
  DJ.player.on(function (kind) {
    if (kind === 'tick') return;
    DJ.$$('.track-card').forEach(function (c) { if (c._sync) c._sync(); });
  });

  /* =====================================================================================
     Inline mini players  <span class="mp" data-src="music/..." data-title="...">
     ===================================================================================== */
  DJ.miniPlayer = function (host, item, opts) {
    opts = opts || {};
    var playable = DJ.playable(item) && !(host.dataset && host.dataset.missing);
    var meta = [];
    if (item.bpm) meta.push(DJ.fmtBpm(item.bpm) + ' BPM');
    if (item.duration_sec) meta.push(DJ.fmtTime(item.duration_sec));
    var title = opts.title || item.title_he || item.title || (item.file || '').split('/').pop();
    var ui = DJ.h('<span class="mp-ui" role="group" aria-label="נגן: ' + esc(title) + '">' +
      '<button class="mp-btn" type="button" ' + (playable ? '' : 'disabled ') + 'aria-label="ניגון ' + esc(title) + '">' + I('play') + '</button>' +
      '<span class="mp-head"><span class="mp-title">' + esc(title) + '</span>' + (playable ? '<span class="mp-meta">' + esc(meta.join(' · ')) + '</span>' : '<span class="badge badge--soon mp-soon">בקרוב</span>') + '</span>' +
      '<span class="mp-wave"><canvas aria-hidden="true"></canvas></span>' +
      (playable ? '<a class="icon-btn icon-btn--sm mp-dl" href="' + esc(DJ.media(item.file)) + '" download aria-label="הורדה" title="הורדה">' + I('download') + '</a>' : '<span class="mp-dl"></span>') +
      '</span>');
    host.innerHTML = ''; host.appendChild(ui);
    var btn = ui.querySelector('.mp-btn'), cv = ui.querySelector('canvas');
    var w = new DJ.Wave(cv, {
      peaks: DJ.peaks(item.file), seed: (item.id || title).length, barW: 2, gap: 0.5,
      onSeek: playable ? function (f) {
        var d = item.duration_sec || DJ.player.duration();
        if (!DJ.player.isCurrent(item.file)) DJ.player.play(item, { queue: opts.queue ? opts.queue() : [item], startAt: f * d });
        else DJ.player.seek(f * DJ.player.duration());
      } : null
    });
    cv._wave = w;
    btn.addEventListener('click', function () { DJ.player.play(item, { queue: opts.queue ? opts.queue() : [item] }); });
    function sync(kind) {
      var curr = DJ.player.isCurrent(item.file), on = DJ.player.isPlaying(item.file);
      if (kind !== 'tick') {
        ui.classList.toggle('is-current', curr);
        btn.innerHTML = I(on ? 'pause' : 'play');
        btn.setAttribute('aria-label', (on ? 'השהיה ' : 'ניגון ') + title);
        if (!curr) w.set(0);
      }
      if (curr) { var d = DJ.player.duration(); w.set(d ? DJ.player.time() / d : 0); }
    }
    DJ.player.on(sync);
    return ui;
  };

  function hydrateMini() {
    DJ.$$('.mp[data-src]').forEach(function (host) {
      var src = host.getAttribute('data-src');
      var item = DJ.byFile.get(src) || { id: src, file: src, title: host.getAttribute('data-title') || src, has_audio: !host.dataset.missing };
      DJ.miniPlayer(host, item, { title: host.getAttribute('data-title') || null });
    });
    DJ.$$('.tref[data-file]').forEach(function (el) {
      var f = el.getAttribute('data-file'), t = DJ.byFile.get(f);
      if (t && DJ.playable(t)) {
        var b = DJ.h('<button type="button" class="tref-btn" title="' + esc(f) + '"><span class="ico">' + I('play') + '</span><span class="t">' + esc(t.title || f.split('/').pop()) + '</span></button>');
        b.addEventListener('click', function () { DJ.player.play(t); });
        el.replaceWith(b);
      } else if (!el.dataset.missing) {
        var it = { id: f, file: f, title: f.split('/').pop().replace(/\.[^.]+$/, ''), has_audio: true };
        var b2 = DJ.h('<button type="button" class="tref-btn" title="' + esc(f) + '"><span class="ico">' + I('play') + '</span><span class="t">' + esc(it.title) + '</span></button>');
        b2.addEventListener('click', function () { DJ.player.play(it); });
        el.replaceWith(b2);
      } else {
        var stem = f.split('/').pop().replace(/\.[^.]+$/, '');
        var pl = (DJ.catalog.plan.tracks || []).filter(function (x) { return x.file_stem === stem; })[0] || DJ.planById.get(stem);
        var lab = pl ? pl.title : stem;
        el.replaceWith(DJ.h('<button type="button" class="tref-btn" disabled title="' + esc(f) + ' - הקובץ עדיין ברינדור"><span class="ico">' + I('play') + '</span><span class="t">' + esc(lab) + '</span></button>'));
      }
    });
    DJ.$$('.tref[data-id]').forEach(function (el) {
      var id = el.getAttribute('data-id'), t = DJ.byId.get(id), p = t || DJ.planById.get(id);
      if (!p) return;
      if (t && DJ.playable(t)) {
        var b = DJ.h('<button type="button" class="tref-btn" title="' + esc(id) + ' · ' + esc(t.genre || '') + ' ' + (t.bpm ? DJ.fmtBpm(t.bpm) + ' BPM' : '') + '"><span class="ico">' + I('play') + '</span><span class="t">' + esc(t.title) + '</span></button>');
        b.addEventListener('click', function () { DJ.player.play(t); });
        el.replaceWith(b);
      } else {
        el.replaceWith(DJ.h('<button type="button" class="tref-btn" disabled title="' + esc(id) + ' · ' + esc(p.title_he || '') + ' - בקרוב"><span class="ico">' + I('play') + '</span><span class="t">' + esc(p.title || id) + '</span></button>'));
      }
    });
  }
  DJ.ready(hydrateMini);

  /* =====================================================================================
     Track details drawer
     ===================================================================================== */
  var drawer = null;
  function ensureDrawer() {
    if (drawer) return drawer;
    drawer = DJ.h('<dialog class="drawer" aria-labelledby="drawer-title"><div class="drawer-head"><h2 id="drawer-title">פרטי טראק</h2><button class="icon-btn" type="button" data-close aria-label="סגירה">' + I('close') + '</button></div><div class="drawer-body"></div></dialog>');
    doc.body.appendChild(drawer);
    drawer.querySelector('[data-close]').addEventListener('click', function () { drawer.close(); });
    drawer.addEventListener('click', function (e) { if (e.target === drawer) drawer.close(); });
    drawer.addEventListener('close', function () {
      if (DJ.params.has('track')) { try { var u = new URL(location.href); u.searchParams.delete('track'); history.replaceState(null, '', u); } catch (e) { /* ignore */ } }
    });
    return drawer;
  }

  DJ.openTrack = function (id, opts) {
    opts = opts || {};
    var t = DJ.byId.get(id) || DJ.planById.get(id);
    if (!t) return;
    if (!doc.body.classList.contains('page-library') && !DJ.byId.get(id) && !opts.force) { location.href = DJ.page('library.html?track=' + encodeURIComponent(id)); return; }
    ensureDrawer();
    var body = drawer.querySelector('.drawer-body');
    var cam = DJ.camOf(t), playable = DJ.playable(t), d = t.duration_sec || 0;
    var facts = [['BPM', DJ.fmtBpm(t.bpm)], ['Key', t.key_short || t.key || '—'], ['Camelot', cam || '—'], ['אורך', d ? DJ.fmtTime(d) : '—']];
    var sections = (t.sections || []).map(function (s) {
      var len = s.bars || 8, e = s.energy != null ? s.energy : 5;
      return '<span style="flex:' + len + ';--e:' + e + '" title="' + esc(s.name) + ' · ' + len + ' תיבות · תיבה ' + ((s.start_bar || 0) + 1) + '">' + esc(s.name) + '</span>';
    }).join('');
    var cues = (t.cues || []).map(function (c) {
      return '<li><button type="button" data-seek="' + c.sec + '" style="--c:' + esc(c.color || DJ.CUE_COLORS[c.slot]) + '"><span class="cue-slot">' + esc(c.slot) + '</span><span>' + esc(c.name || '') + '</span><span class="cue-time">' + (c.bar != null ? 'Bar ' + (c.bar + 1) + ' · ' : '') + DJ.fmtTime(c.sec) + '</span></button></li>';
    }).join('');
    var mem = (t.memory_cues || []).map(function (c) {
      return '<li><button type="button" data-seek="' + c.sec + '" style="--c:#e8e8f0"><span class="cue-slot" style="background:transparent;border:1.5px solid var(--border-strong);color:var(--text)">M</span><span>' + esc(c.name || '') + '</span><span class="cue-time">' + DJ.fmtTime(c.sec) + '</span></button></li>';
    }).join('');
    var inst = (t.instruments || []).map(function (x) { return '<span class="chip chip--static chip--sm">' + esc(x) + '</span>'; }).join('');
    var compat = playable || t.bpm ? DJ.compatibleTracks(t, { limit: 8 }) : [];
    var compatHTML = compat.length ? compat.map(function (c) {
      var o = c.track;
      return '<li class="compat-item"><span class="ci-art">' + DJ.coverHTML(o) + '</span><span class="ci-main"><button type="button" class="ci-title" data-open="' + esc(o.id) + '">' + esc(o.title) + '</button>' +
        '<span class="ci-why"><span class="why why--' + c.rel.type + '">' + esc(c.rel.label) + '</span><span dir="ltr">' + DJ.fmtBpm(o.bpm) + ' BPM (' + esc(c.bpm.label) + ')</span><span>' + esc(o.genre || '') + '</span></span></span>' +
        '<span class="ci-side">' + DJ.camBadge(DJ.camOf(o)) + '<button type="button" class="icon-btn icon-btn--sm icon-btn--solid" data-play="' + esc(o.id) + '" aria-label="ניגון ' + esc(o.title) + '">' + I('play') + '</button></span></li>';
    }).join('') : '<li class="muted small">' + (DJ.tracksReady().length > 1 ? 'אין עדיין טראק מתאים בטווח ±6% ובסולם תואם. נסו את גלגל הקאמלוט.' : 'ההמלצות יופיעו כשיהיו עוד טראקים בספרייה.') + '</li>';

    body.innerHTML =
      '<div class="dt-top" style="--cam:' + DJ.cam.color(cam) + '"><div class="dt-cover">' + DJ.coverHTML(t, { alt: 'עטיפה: ' + (t.title || '') }) + '</div><div>' +
      '<p class="dt-title">' + esc(t.title || t.id) + '</p><p class="dt-he">' + esc(t.title_he || '') + '</p>' +
      '<div class="chip-row"><span class="chip chip--static chip--sm">' + esc(t.genre || '') + '</span>' + (t.family ? '<span class="chip chip--static chip--sm" data-family="' + esc(t.family) + '">' + esc(DJ.FAMILIES[t.family] || t.family) + '</span>' : '') + '</div>' +
      '<div class="tc-meta" style="margin-top:10px">' + DJ.roleHTML(t.role) + DJ.energyHTML(t.energy) + (playable ? '' : '<span class="badge badge--soon">בקרוב</span>') + '</div>' +
      '</div></div>' +
      '<div class="dt-facts">' + facts.map(function (f) { return '<div><span class="k">' + f[0] + '</span><span class="v">' + esc(f[1]) + '</span></div>'; }).join('') + '</div>' +
      '<div class="btn-row">' +
      (playable ? '<button class="btn btn--primary btn--sm" type="button" data-play-main>' + I('play') + '<span>ניגון</span></button>' +
        '<a class="btn btn--ghost btn--sm" href="' + esc(DJ.media(t.file)) + '" download>' + I('download') + '<span>MP3' + (t.size_bytes ? ' · ' + DJ.fmtSize(t.size_bytes) : '') + '</span></a>' : '') +
      '<a class="btn btn--ghost btn--sm" href="' + DJ.page('tools/mix-trainer.html?a=' + encodeURIComponent(t.id) + (compat[0] ? '&b=' + encodeURIComponent(compat[0].track.id) : '')) + '">' + I('mixer') + '<span>למאמן המיקס</span></a>' +
      '<a class="btn btn--ghost btn--sm" href="' + DJ.page('tools/set-builder.html?add=' + encodeURIComponent(t.id)) + '">' + I('plus') + '<span>הוספה לסט</span></a>' +
      '</div>' +
      (playable && d ? '<div class="dt-section"><h3>מבנה הטראק</h3><div class="dt-wave"><canvas aria-label="Waveform - לחצו כדי לנגן מנקודה"></canvas></div>' + (sections ? '<div class="dt-sections" aria-hidden="true">' + sections + '</div>' : '') + '</div>' : '') +
      (t.description_he ? '<div class="dt-section"><h3>על הטראק</h3><p>' + esc(t.description_he) + '</p></div>' : '') +
      (t.mix_tips_he ? '<div class="dt-section"><aside class="callout callout--exercise" role="note" style="margin:0"><div class="callout-head">' + I('headphones') + '<span>טיפ ערבוב</span></div><div class="callout-body"><p>' + esc(t.mix_tips_he) + '</p></div></aside></div>' : '') +
      (cues ? '<div class="dt-section"><h3>Hot Cues</h3><ul class="cue-list">' + cues + '</ul></div>' : '') +
      (mem ? '<div class="dt-section"><h3>Memory Cues</h3><ul class="cue-list">' + mem + '</ul></div>' : '') +
      '<div class="dt-section" data-compat-section><h3>מתאימים למיקס <span class="muted small">(Camelot תואם · BPM ±6%)</span></h3><ul class="compat-list">' + compatHTML + '</ul></div>' +
      (inst ? '<div class="dt-section"><h3>כלים בטראק</h3><div class="chip-row inst-chips">' + inst + '</div></div>' : '') +
      (t.lufs != null ? '<p class="muted small" dir="rtl">Loudness: <span dir="ltr">' + esc(t.lufs) + ' LUFS · ' + esc(t.true_peak_dbtp) + ' dBTP</span> · רישיון CC0 · ' + esc(t.id) + '</p>' : '');

    var playMain = body.querySelector('[data-play-main]');
    if (playMain) playMain.addEventListener('click', function () { DJ.player.play(t, { startAt: DJ.player.isCurrent(t.file) ? null : 0 }); });
    body.querySelectorAll('[data-seek]').forEach(function (b) {
      b.addEventListener('click', function () {
        var s = +b.getAttribute('data-seek');
        if (DJ.player.isCurrent(t.file)) { DJ.player.seek(s); DJ.player.resume(); } else DJ.player.play(t, { startAt: s });
      });
    });
    body.querySelectorAll('[data-open]').forEach(function (b) { b.addEventListener('click', function () { DJ.openTrack(b.getAttribute('data-open')); }); });
    body.querySelectorAll('[data-play]').forEach(function (b) { b.addEventListener('click', function () { var o = DJ.byId.get(b.getAttribute('data-play')); if (o) DJ.player.play(o); }); });
    var cv = body.querySelector('.dt-wave canvas');
    if (!drawer.open) { try { drawer.showModal(); } catch (e) { drawer.setAttribute('open', ''); } }
    if (cv) {
      var marks = (t.cues || []).map(function (c) { return { f: c.sec / d, color: c.color || DJ.CUE_COLORS[c.slot] }; });
      var w = new DJ.Wave(cv, {
        peaks: DJ.peaks(t.file), marks: marks, barW: 2, gap: 0.5,
        onSeek: function (f) { if (DJ.player.isCurrent(t.file)) DJ.player.seek(f * DJ.player.duration()); else DJ.player.play(t, { startAt: f * d }); }
      });
      var sync = function () { if (drawer.open && DJ.player.isCurrent(t.file)) { var dd = DJ.player.duration(); w.set(dd ? DJ.player.time() / dd : 0); } };
      DJ.player.on(sync); sync();
    }
    if (opts.focus === 'compat') { var s = body.querySelector('[data-compat-section]'); if (s) s.scrollIntoView({ block: 'start' }); }
    drawer.scrollTop = opts.focus === 'compat' ? drawer.scrollTop : 0;
  };

  /* =====================================================================================
     Energy chart (SVG line+area, role-coloured dots, hover tooltip)
     ===================================================================================== */
  var ROLE_COL = { warmup: '#22e1ff', build: '#b6ff3b', peak: '#ff2bd6', closing: '#8a5cff' };
  DJ.energyChart = function (host, tracks, opts) {
    opts = opts || {};
    host.innerHTML = '';
    if (!tracks.length) { host.innerHTML = '<p class="ec-empty">' + (opts.empty || 'הוסיפו טראקים כדי לראות את עקומת האנרגיה') + '</p>'; return; }
    var W = Math.max(280, host.clientWidth || 600), H = opts.height || 200, padL = 28, padR = 14, padT = 16, padB = 28;
    var iw = W - padL - padR, ih = H - padT - padB, n = tracks.length;
    var x = function (i) { return padL + (n === 1 ? iw / 2 : (i * iw) / (n - 1)); };
    var y = function (e) { return padT + ih - (DJ.clamp(e || 0, 0, 10) / 10) * ih; };
    var pts = tracks.map(function (t, i) { return [x(i), y(t.energy)]; });
    var line = pts.map(function (p, i) { return (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1); }).join(' ');
    var area = line + ' L' + pts[n - 1][0].toFixed(1) + ' ' + (padT + ih) + ' L' + pts[0][0].toFixed(1) + ' ' + (padT + ih) + ' Z';
    var grid = '';
    [0, 5, 10].forEach(function (e) { grid += '<line x1="' + padL + '" x2="' + (W - padR) + '" y1="' + y(e) + '" y2="' + y(e) + '"/><text x="' + (padL - 8) + '" y="' + (y(e) + 4) + '" text-anchor="end">' + e + '</text>'; });
    var xl = '';
    var every = Math.ceil(n / 12);
    tracks.forEach(function (t, i) { if (i % every === 0 || i === n - 1) xl += '<text x="' + x(i) + '" y="' + (H - 8) + '" text-anchor="middle">' + (i + 1) + '</text>'; });
    var gid = 'ec-grad-' + Math.random().toString(36).slice(2, 7);
    var dots = tracks.map(function (t, i) {
      return '<circle class="ec-dot" tabindex="0" r="5" cx="' + pts[i][0].toFixed(1) + '" cy="' + pts[i][1].toFixed(1) + '" fill="' + (ROLE_COL[t.role] || '#ff2bd6') + '" data-i="' + i + '" aria-label="' + (i + 1) + '. ' + esc(t.title) + ' · אנרגיה ' + (t.energy || '?') + '"/>';
    }).join('');
    host.innerHTML = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="עקומת אנרגיה: ' + tracks.map(function (t) { return t.energy; }).join(', ') + '">' +
      '<defs><linearGradient id="' + gid + '" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ff2bd6" stop-opacity=".35"/><stop offset="1" stop-color="#ff2bd6" stop-opacity="0"/></linearGradient></defs>' +
      '<g class="ec-grid">' + grid + '</g><g class="ec-x">' + xl + '</g>' +
      '<path d="' + area + '" fill="url(#' + gid + ')"/><path class="ec-line" d="' + line + '"/>' + dots + '</svg>';
    var tip = DJ.h('<div class="ec-tip" hidden></div>');
    host.appendChild(tip);
    var svg = host.querySelector('svg');
    function show(el) {
      var i = +el.getAttribute('data-i'), t = tracks[i];
      var r = svg.getBoundingClientRect(), sx = r.width / W;
      tip.innerHTML = '<b>' + (i + 1) + '. ' + esc(t.title) + '</b><br>' + esc(t.genre || '') + ' · <span dir="ltr">' + DJ.fmtBpm(t.bpm) + ' BPM · ' + (DJ.camOf(t) || '') + '</span><br>אנרגיה ' + (t.energy || '?') + '/10 · ' + esc(DJ.ROLES[t.role] || '');
      tip.style.left = (pts[i][0] * sx) + 'px'; tip.style.top = (pts[i][1] * sx) + 'px';
      tip.hidden = false;
    }
    host.querySelectorAll('.ec-dot').forEach(function (d) {
      d.addEventListener('mouseenter', function () { show(d); });
      d.addEventListener('focus', function () { show(d); });
      d.addEventListener('mouseleave', function () { tip.hidden = true; });
      d.addEventListener('blur', function () { tip.hidden = true; });
      d.addEventListener('click', function () { var t = tracks[+d.getAttribute('data-i')]; if (opts.onClick) opts.onClick(t); else if (DJ.playable(t)) DJ.player.play(t, { queue: tracks }); });
    });
  };
  DJ.sparkline = function (tracks) {
    if (!tracks.length) return '';
    var W = 300, H = 64, n = tracks.length;
    var pts = tracks.map(function (t, i) { return [(n === 1 ? W / 2 : i * W / (n - 1)), H - 6 - (DJ.clamp(t.energy || 0, 0, 10) / 10) * (H - 12)]; });
    var d = pts.map(function (p, i) { return (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1); }).join(' ');
    var gid = 'sp' + Math.random().toString(36).slice(2, 7);
    return '<svg viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none" aria-hidden="true"><defs><linearGradient id="' + gid + '" x1="0" x2="1"><stop offset="0" stop-color="#22e1ff"/><stop offset=".5" stop-color="#8a5cff"/><stop offset="1" stop-color="#ff2bd6"/></linearGradient></defs>' +
      '<path d="' + d + ' L' + W + ' ' + H + ' L0 ' + H + ' Z" fill="url(#' + gid + ')" opacity=".15"/><path d="' + d + '" fill="none" stroke="url(#' + gid + ')" stroke-width="2.5" stroke-linejoin="round" vector-effect="non-scaling-stroke"/></svg>';
  };
})();
