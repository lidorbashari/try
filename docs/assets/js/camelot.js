/* DJ Lab — interactive Camelot wheel: select a key, see compatible keys, our tracks and crate tracks in them. */
(function () {
  'use strict';
  var DJ = window.DJ, I = DJ.icon, esc = DJ.esc;
  var NS = 'http://www.w3.org/2000/svg';
  var CX = 210, CY = 210, R_OUT = 200, R_MID = 142, R_IN = 86;
  var REL_ORDER = ['perfect', 'adjacent', 'relative', 'boost'];
  var REL_HE = { perfect: 'אותו סולם', adjacent: 'שכנים (±1)', relative: 'יחסי (A↔B)', boost: 'Energy Boost (+2 / +7)' };
  var REL_DESC = {
    perfect: 'הכי בטוח - אותו סולם בדיוק.',
    adjacent: 'מעבר חלק כמעט תמיד. +1 מרים קצת, −1 מוריד קצת.',
    relative: 'מעבר בין מינור למז\'ור באותם תווים - משנה את מצב הרוח.',
    boost: '+2 מרגיש כמו "הרמה", +7 הוא חצי טון למעלה - דרמטי, לשימוש במינון.'
  };

  function pt(r, deg) { var a = (deg - 90) * Math.PI / 180; return [CX + r * Math.cos(a), CY + r * Math.sin(a)]; }
  function sector(r0, r1, a0, a1) {
    var p0 = pt(r1, a0), p1 = pt(r1, a1), p2 = pt(r0, a1), p3 = pt(r0, a0);
    return 'M' + p0 + ' A' + r1 + ' ' + r1 + ' 0 0 1 ' + p1 + ' L' + p2 + ' A' + r0 + ' ' + r0 + ' 0 0 0 ' + p3 + ' Z';
  }

  DJ.ready(function () {
    var tool = DJ.$('[data-camelot-tool]');
    if (!tool) return;
    var wheelHost = DJ.$('[data-wheel]'), info = DJ.$('[data-key-info]'), tracksBox = DJ.$('[data-key-tracks]'), cratesBox = DJ.$('[data-key-crates]');
    var ours = DJ.tracksReady().length ? DJ.tracksReady() : DJ.catalog.tracks.concat((DJ.catalog.plan.tracks || []).filter(function (p) { return !DJ.byId.has(p.id); }));
    var crateRows = [];
    (window.DJLAB_CRATES || []).forEach(function (c) { (c.tracks || []).forEach(function (r) { var cam = DJ.cam.norm(r.camelot) || DJ.cam.fromKey(r.key); if (cam) crateRows.push({ r: r, cam: cam, crate: c }); }); });
    var counts = {};
    ours.forEach(function (t) { var c = DJ.camOf(t); if (c) counts[c] = (counts[c] || 0) + 1; });
    var sel = DJ.cam.norm(DJ.params.get('key')) || DJ.cam.fromKey(DJ.params.get('key')) || DJ.store.get('cam-key', '8A');

    var svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', '0 0 420 420'); svg.setAttribute('class', 'wheel');
    svg.setAttribute('role', 'group'); svg.setAttribute('aria-label', 'גלגל קאמלוט - 24 סולמות. חצים לניווט, Enter לבחירה');
    var segs = {};
    for (var n = 1; n <= 12; n++) {
      ['B', 'A'].forEach(function (l) {
        var code = n + l, a0 = n * 30 - 15, a1 = n * 30 + 15;
        var r0 = l === 'B' ? R_MID : R_IN, r1 = l === 'B' ? R_OUT : R_MID;
        var g = document.createElementNS(NS, 'g');
        g.setAttribute('class', 'seg seg-' + l.toLowerCase()); g.setAttribute('tabindex', code === sel ? '0' : '-1'); g.setAttribute('role', 'button');
        g.setAttribute('data-code', code);
        g.setAttribute('aria-label', code + ' · ' + DJ.cam.names[code] + ' · ' + (counts[code] || 0) + ' טראקים שלנו');
        g.style.setProperty('--cam', DJ.cam.color(code));
        var path = document.createElementNS(NS, 'path'); path.setAttribute('d', sector(r0 + 1.5, r1 - 1.5, a0 + 0.8, a1 - 0.8)); path.setAttribute('class', 'seg-path');
        var rm = (r0 + r1) / 2, p = pt(rm, n * 30);
        var t1 = document.createElementNS(NS, 'text'); t1.setAttribute('x', p[0]); t1.setAttribute('y', p[1] - 2); t1.setAttribute('class', 'seg-code'); t1.textContent = code;
        var t2 = document.createElementNS(NS, 'text'); t2.setAttribute('x', p[0]); t2.setAttribute('y', p[1] + 13); t2.setAttribute('class', 'seg-key'); t2.textContent = DJ.cam.keys[code];
        g.appendChild(path); g.appendChild(t1); g.appendChild(t2);
        if (counts[code]) {
          var dp = pt(l === 'B' ? R_OUT - 12 : R_IN + 11, n * 30 + 10);
          var dot = document.createElementNS(NS, 'circle'); dot.setAttribute('cx', dp[0]); dot.setAttribute('cy', dp[1]); dot.setAttribute('r', 7.5); dot.setAttribute('class', 'seg-dot');
          var dt = document.createElementNS(NS, 'text'); dt.setAttribute('x', dp[0]); dt.setAttribute('y', dp[1] + 3.2); dt.setAttribute('class', 'seg-count'); dt.textContent = counts[code];
          g.appendChild(dot); g.appendChild(dt);
        }
        svg.appendChild(g); segs[code] = g;
      });
    }
    var hub = document.createElementNS(NS, 'g'); hub.setAttribute('class', 'hub');
    hub.innerHTML = '<circle cx="' + CX + '" cy="' + CY + '" r="' + (R_IN - 6) + '" class="hub-bg"/><text x="' + CX + '" y="' + (CY + 2) + '" class="hub-code" data-hub-code></text><text x="' + CX + '" y="' + (CY + 26) + '" class="hub-name" data-hub-name></text>';
    svg.appendChild(hub);
    wheelHost.appendChild(svg);
    DJ.$('[data-wheel-legend]').innerHTML = REL_ORDER.map(function (r) { return '<span class="lg lg--' + r + '"><i></i>' + REL_HE[r] + '</span>'; }).join('') + '<span class="lg lg--dot"><i></i>מספר הטראקים שלנו בסולם</span>';

    function select(code, focus) {
      sel = code; DJ.store.set('cam-key', code);
      var comp = DJ.cam.compatible(code), map = {};
      comp.forEach(function (c) { if (!map[c.code]) map[c.code] = c; });
      Object.keys(segs).forEach(function (k) {
        var g = segs[k], c = map[k];
        g.classList.toggle('is-sel', k === code);
        g.classList.toggle('is-comp', !!c && k !== code);
        g.classList.toggle('is-dim', !c);
        g.setAttribute('data-rel', c ? c.type : '');
        g.setAttribute('tabindex', k === code ? '0' : '-1');
        g.setAttribute('aria-pressed', String(k === code));
      });
      svg.querySelector('[data-hub-code]').textContent = code;
      svg.querySelector('[data-hub-name]').textContent = DJ.cam.names[code];
      if (focus) segs[code].focus();
      renderInfo(code, comp); renderTracks(code, comp); renderCrates(code, comp);
      try { var u = new URL(location.href); u.searchParams.set('key', code); history.replaceState(null, '', u); } catch (e) { /* */ }
    }
    function relChip(type, label) { return '<span class="why why--' + type + '">' + esc(label) + '</span>'; }
    function renderInfo(code, comp) {
      var p = DJ.cam.parse(code);
      info.innerHTML = '<div class="ki-head">' + DJ.camBadge(code, 'cam-badge--lg') + '<div><h2>' + esc(DJ.cam.names[code]) + '</h2><p class="muted">' + (p.l === 'A' ? 'מינור · הטבעת הפנימית' : 'מז\'ור · הטבעת החיצונית') + ' · בסימון של Rekordbox: <b dir="ltr">' + esc(DJ.cam.keys[code]) + '</b></p></div></div>' +
        '<ul class="ki-list">' + comp.map(function (c) {
          var rel = DJ.cam.relation(code, c.code);
          return '<li><button type="button" data-go="' + c.code + '">' + DJ.camBadge(c.code) + '<span class="ki-key" dir="ltr">' + esc(DJ.cam.keys[c.code]) + '</span>' + relChip(c.type, c.type === 'perfect' ? 'אותו סולם' : rel.label) + '<span class="ki-n">' + (counts[c.code] || 0) + ' טראקים</span></button></li>';
        }).join('') + '</ul>' +
        '<p class="muted small">' + REL_DESC.adjacent + ' ' + REL_DESC.relative + '</p>';
      info.querySelectorAll('[data-go]').forEach(function (b) { b.addEventListener('click', function () { select(b.getAttribute('data-go'), true); }); });
    }
    function renderTracks(code, comp) {
      var rows = [];
      comp.forEach(function (c, i) {
        ours.forEach(function (t) { if (DJ.camOf(t) === c.code && !rows.some(function (r) { return r.t === t; })) rows.push({ t: t, c: c, i: i }); });
      });
      rows.sort(function (a, b) { return REL_ORDER.indexOf(a.c.type) - REL_ORDER.indexOf(b.c.type) || a.t.bpm - b.t.bpm; });
      var q = rows.map(function (r) { return r.t; }).filter(DJ.playable);
      tracksBox.innerHTML = '<div class="kt-head"><h2 class="card-title">' + I('disc') + 'מהספרייה שלנו <span class="muted small">(' + rows.length + ')</span></h2><a class="btn btn--ghost btn--sm" href="' + DJ.page('library.html?camelot=' + code + '&compat=1') + '"><span>לספרייה המסוננת</span>' + I('arrow-left') + '</a></div>' +
        (rows.length ? '<ul class="compat-list">' + rows.map(function (r) {
          var t = r.t, rel = DJ.cam.relation(code, DJ.camOf(t));
          return '<li class="compat-item"><span class="ci-art">' + DJ.coverHTML(t) + '</span><span class="ci-main"><button type="button" class="ci-title" data-open="' + esc(t.id) + '">' + esc(t.title) + '</button><span class="ci-why">' + relChip(rel.type, rel.type === 'perfect' ? 'אותו סולם' : rel.label) + '<span>' + esc(t.genre || '') + '</span><span dir="ltr">' + DJ.fmtBpm(t.bpm) + ' BPM</span>' + (DJ.playable(t) ? '' : '<span class="badge badge--soon">בקרוב</span>') + '</span></span>' +
            '<span class="ci-side">' + DJ.camBadge(DJ.camOf(t)) + (DJ.playable(t) ? '<button type="button" class="icon-btn icon-btn--sm icon-btn--solid" data-play="' + esc(t.id) + '" aria-label="ניגון ' + esc(t.title) + '">' + I('play') + '</button>' : '') + '</span></li>';
        }).join('') + '</ul>' : '<p class="muted">אין לנו עדיין טראקים בסולמות האלה.</p>');
      tracksBox.querySelectorAll('[data-play]').forEach(function (b) { b.addEventListener('click', function () { var t = DJ.byId.get(b.getAttribute('data-play')); DJ.player.play(t, { queue: q }); }); });
      tracksBox.querySelectorAll('[data-open]').forEach(function (b) { b.addEventListener('click', function () { DJ.openTrack(b.getAttribute('data-open')); }); });
    }
    var showAll = false;
    function renderCrates(code, comp) {
      var allowed = {}; comp.forEach(function (c) { if (!allowed[c.code]) allowed[c.code] = c; });
      var rows = crateRows.filter(function (x) { return allowed[x.cam]; });
      rows.sort(function (a, b) { return REL_ORDER.indexOf(allowed[a.cam].type) - REL_ORDER.indexOf(allowed[b.cam].type) || (parseFloat(a.r.bpm) || 0) - (parseFloat(b.r.bpm) || 0); });
      var lim = showAll ? rows.length : 14;
      cratesBox.innerHTML = '<h2 class="card-title">' + I('crate') + 'מהארגזים (שירים אמיתיים) <span class="muted small">(' + rows.length + ')</span></h2>' +
        (crateRows.length ? (rows.length ? '<ul class="crate-rows">' + rows.slice(0, lim).map(function (x) {
          var rel = DJ.cam.relation(code, x.cam);
          return '<li>' + DJ.camBadge(x.cam) + '<span class="cr-main"><b dir="auto">' + esc(x.r.artist) + '</b> <span class="muted">–</span> <span dir="auto">' + esc(x.r.title) + '</span></span><span class="cr-meta"><span dir="ltr">' + esc(x.r.bpm) + ' BPM</span>' + relChip(rel.type, rel.type === 'perfect' ? 'אותו סולם' : rel.label) + '<a href="' + DJ.page(x.crate.href) + '">' + esc(x.crate.title_he) + '</a></span></li>';
        }).join('') + '</ul>' + (rows.length > lim ? '<button type="button" class="btn btn--ghost btn--sm" data-more>להציג את כל ' + rows.length + '</button>' : '') : '<p class="muted">אין שירים מהארגזים בסולמות האלה.</p>')
          : '<p class="muted">הארגזים עוד בבנייה - כשיתווספו, יופיעו כאן שירים אמיתיים בכל סולם.</p>');
      var more = cratesBox.querySelector('[data-more]');
      if (more) more.addEventListener('click', function () { showAll = true; renderCrates(code, comp); });
    }

    svg.addEventListener('click', function (e) { var g = e.target.closest('.seg'); if (g) select(g.getAttribute('data-code'), false); });
    svg.addEventListener('keydown', function (e) {
      var p = DJ.cam.parse(sel), next = null;
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown' && false) next = DJ.cam.code(p.n + 1, p.l);
      else if (e.key === 'ArrowLeft') next = DJ.cam.code(p.n - 1, p.l);
      else if (e.key === 'ArrowUp') next = p.n + 'B';
      else if (e.key === 'ArrowDown') next = p.n + 'A';
      else if (e.key === 'Enter' || e.key === ' ') { var g = e.target.closest('.seg'); if (g) { e.preventDefault(); select(g.getAttribute('data-code'), true); } return; }
      if (next) { e.preventDefault(); select(next, true); }
    });
    select(sel, false);
  });
})();
