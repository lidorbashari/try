/* DJ Lab — Set Builder: ordered set, per-transition compatibility, energy curve, M3U8 / text export. */
(function () {
  'use strict';
  var DJ = window.DJ, I = DJ.icon, esc = DJ.esc;

  DJ.ready(function () {
    var app = DJ.$('[data-setbuilder]');
    if (!app) return;
    var pool = DJ.catalog.tracks.concat((DJ.catalog.plan.tracks || []).filter(function (p) { return !DJ.byId.has(p.id); }).map(function (p) { return Object.assign({ has_audio: false, kind: 'track' }, p); }));
    var byId = new Map(pool.map(function (t) { return [t.id, t]; }));
    var saved = DJ.store.get('set-current', null) || {};
    var st = { name: saved.name || 'הסט שלי', ids: (saved.ids || []).filter(function (id) { return byId.has(id); }), q: '', fam: '' };
    var P = DJ.params;
    if (P.get('load')) { st.ids = P.get('load').split(',').filter(function (id) { return byId.has(id); }); st.name = P.get('name') || 'סט לדוגמה'; }
    if (P.get('add') && byId.has(P.get('add')) && st.ids.indexOf(P.get('add')) < 0) st.ids.push(P.get('add'));

    var listEl = DJ.$('[data-sb-list]'), setEl = DJ.$('[data-sb-set]'), sumEl = DJ.$('[data-sb-summary]'), chartEl = DJ.$('[data-sb-chart]'), nameEl = DJ.$('[data-sb-name]'), sugEl = DJ.$('[data-sb-suggest]');
    nameEl.value = st.name;
    function save() { DJ.store.set('set-current', { name: st.name, ids: st.ids }); }
    function tracks() { return st.ids.map(function (id) { return byId.get(id); }).filter(Boolean); }
    function dur(t) { return t.duration_sec || (t.target_minutes ? t.target_minutes * 60 : 0); }

    /* picker */
    var fams = DJ.FAMILY_ORDER.filter(function (f) { return pool.some(function (t) { return t.family === f; }); });
    var famHost = DJ.$('[data-sb-fams]');
    famHost.innerHTML = '<button type="button" class="chip chip--sm" aria-pressed="true" data-fam="">הכל</button>' + fams.map(function (f) { return '<button type="button" class="chip chip--sm" aria-pressed="false" data-fam="' + f + '">' + esc(DJ.FAMILIES[f]) + '</button>'; }).join('');
    famHost.addEventListener('click', function (e) {
      var b = e.target.closest('[data-fam]'); if (!b) return;
      st.fam = b.getAttribute('data-fam');
      famHost.querySelectorAll('[data-fam]').forEach(function (x) { x.setAttribute('aria-pressed', String(x === b)); });
      renderPicker();
    });
    DJ.$('[data-sb-search]').addEventListener('input', DJ.debounce(function (e) { st.q = e.target.value.trim().toLowerCase(); renderPicker(); }, 120));

    function relTo(prev, t) {
      if (!prev) return '';
      var r = DJ.cam.relation(DJ.camOf(prev), DJ.camOf(t)), b = DJ.bpmRelation(prev.bpm, t.bpm, 6);
      return '<span class="why why--' + r.type + '">' + esc(r.type === 'perfect' ? 'אותו סולם' : r.label) + '</span>' + (b ? '<span class="why ' + (b.type === 'far' ? 'why--clash' : 'why--adjacent') + '" dir="ltr">' + esc(b.label) + '</span>' : '');
    }
    function pickRow(t, prev) {
      var inSet = st.ids.indexOf(t.id) >= 0;
      return '<li class="sb-item' + (inSet ? ' is-in' : '') + '"><span class="ci-art">' + DJ.coverHTML(t) + '</span><span class="ci-main"><span class="ci-title">' + esc(t.title) + '</span>' +
        '<span class="ci-why"><span>' + esc(t.genre || '') + '</span><span dir="ltr">' + DJ.fmtBpm(t.bpm) + '</span>' + DJ.energyHTML(t.energy) + relTo(prev, t) + '</span></span>' +
        '<span class="ci-side">' + DJ.camBadge(DJ.camOf(t)) + '<button type="button" class="icon-btn icon-btn--sm ' + (inSet ? 'icon-btn--solid' : 'icon-btn--accent') + '" data-add="' + esc(t.id) + '" aria-label="' + (inSet ? 'כבר בסט: ' : 'הוספה לסט: ') + esc(t.title) + '"' + (inSet ? ' disabled' : '') + '>' + I(inSet ? 'check' : 'plus') + '</button></span></li>';
    }
    function renderPicker() {
      var ts = tracks(), prev = ts[ts.length - 1];
      var list = pool.filter(function (t) {
        if (st.fam && t.family !== st.fam) return false;
        if (st.q && [t.title, t.title_he, t.genre, DJ.camOf(t), String(t.bpm)].join(' ').toLowerCase().indexOf(st.q) < 0) return false;
        return true;
      });
      listEl.innerHTML = list.map(function (t) { return pickRow(t, prev); }).join('') || '<li class="muted small" style="padding:12px">לא נמצאו טראקים</li>';
      // suggestions after the last track
      if (prev) {
        var sug = DJ.compatibleTracks(prev, { pool: pool.filter(function (t) { return st.ids.indexOf(t.id) < 0; }) })
          .sort(function (a, b) { var ea = (a.track.energy || 5) - (prev.energy || 5), eb = (b.track.energy || 5) - (prev.energy || 5); return (b.score + (eb >= 0 && eb <= 1 ? 6 : 0)) - (a.score + (ea >= 0 && ea <= 1 ? 6 : 0)); }).slice(0, 4);
        sugEl.hidden = !sug.length;
        sugEl.innerHTML = '<h3>' + I('wand') + 'מתאימים אחרי "' + esc(prev.title) + '"</h3><ul class="sb-list">' + sug.map(function (s) { return pickRow(s.track, prev); }).join('') + '</ul>';
      } else sugEl.hidden = true;
    }
    app.addEventListener('click', function (e) {
      var b = e.target.closest('[data-add]');
      if (b && !b.disabled) { var id = b.getAttribute('data-add'); if (st.ids.indexOf(id) < 0) { st.ids.push(id); update(); DJ.toast('נוסף לסט: ' + byId.get(id).title); } }
    });

    /* set list */
    function verdict(a, b) {
      var r = DJ.cam.relation(DJ.camOf(a), DJ.camOf(b)), br = DJ.bpmRelation(a.bpm, b.bpm, 6);
      var keyOk = r.score >= 2, bpmOk = br && br.type !== 'far';
      var tech;
      if (!bpmOk) tech = 'הפרש BPM גדול: מעבר Echo Out, Cut על דרופ, או טראק ביניים.';
      else if (!keyOk) tech = 'הסולמות מתנגשים: מעבר קצר על התופים (Bass Swap מהיר) או בתוך ברייקדאון.';
      else if (r.type === 'boost') tech = 'Energy Boost: היכנסו על הדרופ כדי להרגיש את ההרמה.';
      else if (br.type !== 'ok') tech = 'חצי/כפול טמפו: ערבבו קצר, על פרייז.';
      else tech = 'מעבר חלק: בלנד ארוך של 16–32 תיבות עם Bass Swap.';
      return { r: r, br: br, ok: keyOk && bpmOk, warn: keyOk !== bpmOk, tech: tech };
    }
    function renderSet() {
      var ts = tracks();
      if (!ts.length) { setEl.innerHTML = '<li class="card empty">' + I('setlist', 'empty-icon') + '<h2>הסט ריק</h2><p>הוסיפו טראקים מהרשימה. נתחיל מטראק חימום (אנרגיה נמוכה) ונעלה בהדרגה.</p></li>'; return; }
      var html = '';
      ts.forEach(function (t, i) {
        if (i > 0) {
          var v = verdict(ts[i - 1], t);
          html += '<li class="sb-trans ' + (v.ok ? 'is-ok' : v.warn ? 'is-warn' : 'is-bad') + '" aria-label="מעבר ' + i + '"><span class="tr-icon">' + I(v.ok ? 'check' : 'alert') + '</span>' +
            '<span class="why why--' + v.r.type + '">' + esc(v.r.type === 'perfect' ? 'אותו סולם' : v.r.label) + '</span>' +
            (v.br ? '<span class="why ' + (v.br.type === 'far' ? 'why--clash' : 'why--adjacent') + '" dir="ltr">BPM ' + esc(v.br.label) + '</span>' : '') +
            '<span class="tr-tech">' + esc(v.tech) + '</span></li>';
        }
        html += '<li class="sb-row card" draggable="true" data-i="' + i + '"><span class="sb-grip" aria-hidden="true">' + I('grip') + '</span><span class="sb-num">' + (i + 1) + '</span>' +
          '<span class="ci-art">' + DJ.coverHTML(t) + '</span>' +
          '<span class="ci-main"><button type="button" class="ci-title" data-open="' + esc(t.id) + '">' + esc(t.title) + '</button><span class="ci-why"><span>' + esc(t.genre || '') + '</span><span dir="ltr">' + DJ.fmtBpm(t.bpm) + ' BPM</span>' + DJ.roleHTML(t.role) + (DJ.playable(t) ? '' : '<span class="badge badge--soon">בקרוב</span>') + '</span></span>' +
          '<span class="sb-meta">' + DJ.camBadge(DJ.camOf(t)) + DJ.energyHTML(t.energy) + '<span class="num muted small">' + (dur(t) ? DJ.fmtTime(dur(t)) : '') + '</span></span>' +
          '<span class="sb-ctl">' + (DJ.playable(t) ? '<button type="button" class="icon-btn icon-btn--sm" data-play="' + i + '" aria-label="ניגון ' + esc(t.title) + '">' + I('play') + '</button>' : '') +
          '<button type="button" class="icon-btn icon-btn--sm" data-move="' + i + ':-1" aria-label="הזזה למעלה"' + (i === 0 ? ' disabled' : '') + '>' + I('up') + '</button>' +
          '<button type="button" class="icon-btn icon-btn--sm" data-move="' + i + ':1" aria-label="הזזה למטה"' + (i === ts.length - 1 ? ' disabled' : '') + '>' + I('down') + '</button>' +
          '<button type="button" class="icon-btn icon-btn--sm" data-del="' + i + '" aria-label="הסרה מהסט">' + I('close') + '</button></span></li>';
      });
      setEl.innerHTML = html;
    }
    setEl.addEventListener('click', function (e) {
      var b = e.target.closest('button'); if (!b) return;
      if (b.hasAttribute('data-del')) { st.ids.splice(+b.getAttribute('data-del'), 1); update(); }
      else if (b.hasAttribute('data-move')) {
        var p = b.getAttribute('data-move').split(':'), i = +p[0], j = i + +p[1];
        if (j < 0 || j >= st.ids.length) return;
        var tmp = st.ids[i]; st.ids[i] = st.ids[j]; st.ids[j] = tmp; update();
        var nb = setEl.querySelector('[data-move="' + j + ':' + p[1] + '"]') || setEl.querySelector('[data-move="' + j + ':' + (-p[1]) + '"]'); if (nb) nb.focus();
      } else if (b.hasAttribute('data-play')) { var ts = tracks().filter(DJ.playable); var t = tracks()[+b.getAttribute('data-play')]; DJ.player.play(t, { queue: ts }); }
      else if (b.hasAttribute('data-open')) DJ.openTrack(b.getAttribute('data-open'));
    });
    // drag & drop reorder
    var dragI = null;
    setEl.addEventListener('dragstart', function (e) { var li = e.target.closest('.sb-row'); if (!li) return; dragI = +li.getAttribute('data-i'); li.classList.add('is-drag'); try { e.dataTransfer.setData('text/plain', String(dragI)); e.dataTransfer.effectAllowed = 'move'; } catch (x) { /* */ } });
    setEl.addEventListener('dragover', function (e) { if (dragI === null) return; e.preventDefault(); var li = e.target.closest('.sb-row'); setEl.querySelectorAll('.is-over').forEach(function (x) { x.classList.remove('is-over'); }); if (li) li.classList.add('is-over'); });
    setEl.addEventListener('drop', function (e) {
      e.preventDefault(); var li = e.target.closest('.sb-row'); if (dragI === null || !li) return;
      var to = +li.getAttribute('data-i'), id = st.ids.splice(dragI, 1)[0]; st.ids.splice(to, 0, id); dragI = null; update();
    });
    setEl.addEventListener('dragend', function () { dragI = null; setEl.querySelectorAll('.is-drag,.is-over').forEach(function (x) { x.classList.remove('is-drag', 'is-over'); }); });

    function renderSummary() {
      var ts = tracks(), total = ts.reduce(function (s, t) { return s + dur(t); }, 0);
      var trans = 0, good = 0;
      for (var i = 1; i < ts.length; i++) { trans++; if (verdict(ts[i - 1], ts[i]).ok) good++; }
      var bpms = ts.map(function (t) { return +t.bpm; }).filter(Boolean);
      sumEl.innerHTML = [
        ['טראקים', ts.length], ['משך (בלי חפיפות)', total ? DJ.fmtTime(total) : '—'],
        ['טווח BPM', bpms.length ? '<span dir="ltr">' + DJ.fmtBpm(Math.min.apply(null, bpms)) + '–' + DJ.fmtBpm(Math.max.apply(null, bpms)) + '</span>' : '—'],
        ['מעברים הרמוניים', trans ? good + '/' + trans : '—']
      ].map(function (x) { return '<div><span class="k">' + x[0] + '</span><span class="v">' + x[1] + '</span></div>'; }).join('');
    }
    function update() {
      save(); renderSet(); renderPicker(); renderSummary();
      DJ.energyChart(chartEl, tracks(), { height: 180, onClick: function (t) { if (DJ.playable(t)) DJ.player.play(t, { queue: tracks().filter(DJ.playable) }); else DJ.openTrack(t.id); } });
    }
    nameEl.addEventListener('input', function () { st.name = nameEl.value.trim() || 'הסט שלי'; save(); });

    /* export */
    function absPath(file) {
      var base = DJ.store.get('rbx-path', ''), os = DJ.store.get('rbx-os', 'win');
      if (!base) return file;
      base = String(base).replace(/[\\/]+$/, '');
      var rel = file.replace(/^music\//, '');
      return os === 'win' ? base + '\\' + rel.replace(/\//g, '\\') : base + '/' + rel;
    }
    DJ.$('[data-sb-m3u]').addEventListener('click', function () {
      var ts = tracks().filter(function (t) { return t.file; });
      if (!ts.length) { DJ.toast('אין בסט טראקים עם קבצים'); return; }
      var lines = ['#EXTM3U', '#PLAYLIST:' + st.name];
      ts.forEach(function (t) { lines.push('#EXTINF:' + Math.round(dur(t)) + ',' + (t.artist || 'DJ Lab Originals') + ' - ' + t.title); lines.push(absPath(t.file)); });
      DJ.downloadText((st.name.replace(/[\\/:*?"<>|]+/g, '').trim() || 'djlab-set') + '.m3u8', lines.join('\r\n') + '\r\n', 'audio/x-mpegurl;charset=utf-8');
      DJ.toast(DJ.store.get('rbx-path', '') ? 'נוצר M3U8 עם הנתיבים מהמחולל של Rekordbox' : 'נוצר M3U8 עם נתיבים יחסיים - שמרו אותו בתיקיית DJ-Lab (ליד music)');
    });
    DJ.$('[data-sb-txt]').addEventListener('click', function () {
      var ts = tracks(); if (!ts.length) return;
      var t0 = 0, lines = [st.name, ''];
      ts.forEach(function (t, i) {
        lines.push((i + 1) + '. [' + DJ.fmtTime(t0) + '] ' + t.title + (t.title_he ? ' (' + t.title_he + ')' : '') + ' — ' + (t.genre || '') + ' · ' + DJ.fmtBpm(t.bpm) + ' BPM · ' + (DJ.camOf(t) || '') + ' · Energy ' + (t.energy || '?'));
        t0 += Math.max(0, dur(t) - 16 * 4 * 60 / (t.bpm || 124)); // ~16 bars of overlap per transition
      });
      lines.push('', '(זמנים משוערים: חפיפה של 16 תיבות בכל מעבר)', 'DJ Lab Originals · CC0');
      var text = lines.join('\n');
      DJ.copy(text).then(function () { DJ.toast('הטראקליסט הועתק ללוח'); }, function () { DJ.downloadText('tracklist.txt', text); });
    });
    DJ.$('[data-sb-clear]').addEventListener('click', function () { if (!st.ids.length || window.confirm('לנקות את הסט?')) { st.ids = []; update(); } });
    DJ.$('[data-sb-play]').addEventListener('click', function () { var ts = tracks().filter(DJ.playable); if (ts.length) DJ.player.play(ts[0], { queue: ts }); else DJ.toast('אין בסט טראקים זמינים להאזנה'); });
    window.addEventListener('resize', DJ.debounce(function () { DJ.energyChart(chartEl, tracks(), { height: 180 }); }, 150));
    update();
  });
})();
