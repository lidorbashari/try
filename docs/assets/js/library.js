/* DJ Lab — music library page: filters, sorting, grid/list, genre pack download. */
(function () {
  'use strict';
  var DJ = window.DJ, I = DJ.icon, esc = DJ.esc;

  DJ.ready(function () {
    var root = DJ.$('[data-library]');
    if (!root) return;
    var grid = DJ.$('[data-lib-grid]'), aside = DJ.$('[data-lib-filters]'), countEl = DJ.$('[data-lib-count]'), actions = DJ.$('[data-lib-actions]');

    var catalog = DJ.catalog.tracks.slice();
    var ready = catalog.filter(DJ.playable);
    var soonList = catalog.filter(function (t) { return !DJ.playable(t); }).concat(
      (DJ.catalog.plan.tracks || []).filter(function (p) { return !DJ.byId.has(p.id); }).map(function (p) { return Object.assign({ has_audio: false, kind: 'track' }, p); }));
    var everything = ready.concat(soonList);

    var bpms = everything.map(function (t) { return +t.bpm; }).filter(Boolean);
    var BMIN = bpms.length ? Math.floor(Math.min.apply(null, bpms)) : 60;
    var BMAX = bpms.length ? Math.ceil(Math.max.apply(null, bpms)) : 180;

    var st = {
      q: '', fam: new Set(), genre: new Set(), cam: new Set(), compat: false, role: new Set(),
      bpm: [BMIN, BMAX], energy: [1, 10],
      sort: DJ.store.get('lib-sort', 'default'), view: DJ.store.get('lib-view', 'grid'),
      soon: ready.length === 0
    };
    // deep links
    var P = DJ.params;
    if (P.get('genre')) P.get('genre').split(',').forEach(function (g) { st.genre.add(g); });
    if (P.get('family')) P.get('family').split(',').forEach(function (f) { st.fam.add(f); });
    if (P.get('camelot')) P.get('camelot').split(',').forEach(function (c) { c = DJ.cam.norm(c); if (c) st.cam.add(c); });
    if (P.get('compat')) st.compat = true;
    if (P.get('q')) st.q = P.get('q');
    if (P.get('soon')) st.soon = true;

    function pool() { return st.soon ? everything : ready; }

    /* ---------------- filters UI ---------------- */
    function chip(label, on, extra) {
      return '<button type="button" class="chip" aria-pressed="' + (on ? 'true' : 'false') + '" ' + (extra || '') + '>' + label + '</button>';
    }
    function dualRange(min, max, step, vals, fmt, onInput, label) {
      var el = DJ.h('<div><div class="dual-range"><span class="track"></span><span class="fill"></span>' +
        '<input type="range" min="' + min + '" max="' + max + '" step="' + step + '" value="' + vals[0] + '" aria-label="' + label + ' מינימום">' +
        '<input type="range" min="' + min + '" max="' + max + '" step="' + step + '" value="' + vals[1] + '" aria-label="' + label + ' מקסימום"></div>' +
        '<div class="range-labels"><span>' + fmt(min) + '</span><span>' + fmt(max) + '</span></div></div>');
      var a = el.querySelectorAll('input')[0], b = el.querySelectorAll('input')[1], fill = el.querySelector('.fill');
      function paint() {
        var lo = Math.min(+a.value, +b.value), hi = Math.max(+a.value, +b.value);
        fill.style.left = ((lo - min) / (max - min) * 100) + '%';
        fill.style.right = (100 - (hi - min) / (max - min) * 100) + '%';
        return [lo, hi];
      }
      function h() { onInput(paint()); }
      a.addEventListener('input', h); b.addEventListener('input', h);
      paint();
      el._set = function (v) { a.value = v[0]; b.value = v[1]; paint(); };
      return el;
    }

    var bpmOut, enOut, bpmRange, enRange;
    function buildFilters() {
      var fams = DJ.FAMILY_ORDER.filter(function (f) { return everything.some(function (t) { return t.family === f; }); });
      var roles = ['warmup', 'build', 'peak', 'closing'].filter(function (r) { return everything.some(function (t) { return t.role === r; }); });
      aside.innerHTML =
        '<div class="f-group"><h3>משפחה</h3><div class="chip-row" data-f="fam">' + fams.map(function (f) { return chip(esc(DJ.FAMILIES[f] || f), st.fam.has(f), 'data-v="' + f + '"'); }).join('') + '</div></div>' +
        '<div class="f-group"><h3>ז\'אנר</h3><div class="chip-row" data-f="genre"></div></div>' +
        '<div class="f-group"><h3>BPM <output data-out="bpm"></output></h3><div data-range="bpm"></div></div>' +
        '<div class="f-group"><h3>Camelot <button type="button" class="f-clear" data-clear-cam>ניקוי</button></h3><div class="cam-grid" data-f="cam"></div>' +
        '<label class="switch" style="margin-top:10px"><input type="checkbox" data-compat ' + (st.compat ? 'checked' : '') + '><span></span>כולל סולמות תואמים</label></div>' +
        '<div class="f-group"><h3>אנרגיה <output data-out="energy"></output></h3><div data-range="energy"></div></div>' +
        '<div class="f-group"><h3>תפקיד בסט</h3><div class="chip-row" data-f="role">' + roles.map(function (r) { return chip(esc(DJ.ROLES[r]), st.role.has(r), 'data-v="' + r + '"'); }).join('') + '</div></div>' +
        (soonList.length ? '<div class="f-group"><label class="switch"><input type="checkbox" data-soon ' + (st.soon ? 'checked' : '') + '><span></span>להציג גם טראקים בדרך (' + soonList.length + ')</label></div>' : '') +
        '<div class="f-group"><button type="button" class="btn btn--ghost btn--sm" data-clear-all style="width:100%">ניקוי כל הסינונים</button></div>';
      bpmOut = aside.querySelector('[data-out="bpm"]'); enOut = aside.querySelector('[data-out="energy"]');
      bpmRange = dualRange(BMIN, BMAX, 1, st.bpm, function (v) { return v; }, function (v) { st.bpm = v; update(); }, 'BPM');
      enRange = dualRange(1, 10, 1, st.energy, function (v) { return v; }, function (v) { st.energy = v; update(); }, 'אנרגיה');
      aside.querySelector('[data-range="bpm"]').appendChild(bpmRange);
      aside.querySelector('[data-range="energy"]').appendChild(enRange);
      renderGenreChips(); renderCamGrid();
      aside.querySelector('[data-f="fam"]').addEventListener('click', function (e) {
        var b = e.target.closest('[data-v]'); if (!b) return;
        toggle(st.fam, b.getAttribute('data-v')); b.setAttribute('aria-pressed', st.fam.has(b.getAttribute('data-v')));
        // drop genres that are no longer visible
        if (st.fam.size) st.genre.forEach(function (g) { if (!everything.some(function (t) { return t.genre === g && st.fam.has(t.family); })) st.genre.delete(g); });
        renderGenreChips(); update();
      });
      aside.querySelector('[data-f="role"]').addEventListener('click', function (e) {
        var b = e.target.closest('[data-v]'); if (!b) return;
        toggle(st.role, b.getAttribute('data-v')); b.setAttribute('aria-pressed', st.role.has(b.getAttribute('data-v'))); update();
      });
      aside.querySelector('[data-compat]').addEventListener('change', function (e) { st.compat = e.target.checked; renderCamGrid(); update(); });
      aside.querySelector('[data-clear-cam]').addEventListener('click', function () { st.cam.clear(); renderCamGrid(); update(); });
      var soonBox = aside.querySelector('[data-soon]');
      if (soonBox) soonBox.addEventListener('change', function (e) { st.soon = e.target.checked; renderGenreChips(); update(); });
      aside.querySelector('[data-clear-all]').addEventListener('click', clearAll);
    }
    function toggle(set, v) { if (set.has(v)) set.delete(v); else set.add(v); }
    function renderGenreChips() {
      var host = aside.querySelector('[data-f="genre"]');
      var seen = [], counts = {};
      pool().forEach(function (t) {
        if (st.fam.size && !st.fam.has(t.family)) return;
        if (!t.genre) return;
        if (!counts[t.genre]) { counts[t.genre] = 0; seen.push(t.genre); }
        counts[t.genre]++;
      });
      host.innerHTML = seen.length ? seen.map(function (g) { return chip(esc(g) + ' <small>' + counts[g] + '</small>', st.genre.has(g), 'data-v="' + esc(g) + '"'); }).join('') : '<span class="muted small">—</span>';
      host.onclick = function (e) {
        var b = e.target.closest('[data-v]'); if (!b) return;
        toggle(st.genre, b.getAttribute('data-v')); b.setAttribute('aria-pressed', st.genre.has(b.getAttribute('data-v'))); update();
      };
    }
    function compatSet() {
      var s = new Set();
      st.cam.forEach(function (c) { DJ.cam.compatible(c).forEach(function (x) { s.add(x.code); }); });
      return s;
    }
    function renderCamGrid() {
      var host = aside.querySelector('[data-f="cam"]');
      var order = [];
      ['A', 'B'].forEach(function (l) { for (var n = 1; n <= 12; n++) order.push(n + l); });
      var comp = st.compat ? compatSet() : new Set();
      var present = new Set(pool().map(DJ.camOf));
      host.innerHTML = order.map(function (c) {
        return '<button type="button" style="--cam:' + DJ.cam.color(c) + (present.has(c) ? '' : ';opacity:.45') + '" aria-pressed="' + st.cam.has(c) + '" data-v="' + c + '" class="' + (comp.has(c) && !st.cam.has(c) ? 'is-compat' : '') + '" title="' + c + ' · ' + DJ.cam.names[c] + '">' + c + '</button>';
      }).join('');
      host.onclick = function (e) {
        var b = e.target.closest('[data-v]'); if (!b) return;
        toggle(st.cam, b.getAttribute('data-v')); renderCamGrid(); update();
      };
    }
    function clearAll() {
      st.q = ''; st.fam.clear(); st.genre.clear(); st.cam.clear(); st.role.clear(); st.compat = false;
      st.bpm = [BMIN, BMAX]; st.energy = [1, 10];
      DJ.$('[data-lib-search]').value = '';
      buildFilters(); update();
    }

    /* ---------------- filtering & sorting ---------------- */
    function matches(t) {
      if (st.fam.size && !st.fam.has(t.family)) return false;
      if (st.genre.size && !st.genre.has(t.genre)) return false;
      if (st.role.size && !st.role.has(t.role)) return false;
      var b = +t.bpm || 0;
      if (b && (b < st.bpm[0] || b > st.bpm[1])) return false;
      var e = +t.energy || 0;
      if (e && (e < st.energy[0] || e > st.energy[1])) return false;
      if (st.cam.size) {
        var c = DJ.camOf(t);
        var ok = st.cam.has(c) || (st.compat && compatSet().has(c));
        if (!ok) return false;
      }
      if (st.q) {
        var hay = [t.title, t.title_he, t.genre, t.key, t.key_short, DJ.camOf(t), t.id, DJ.ROLES[t.role], DJ.FAMILIES[t.family], String(t.bpm)].join(' ').toLowerCase();
        var words = st.q.toLowerCase().split(/\s+/).filter(Boolean);
        for (var i = 0; i < words.length; i++) if (hay.indexOf(words[i]) < 0) return false;
      }
      return true;
    }
    var SORTS = {
      'default': null,
      bpm: function (a, b) { return a.bpm - b.bpm; },
      'bpm-desc': function (a, b) { return b.bpm - a.bpm; },
      energy: function (a, b) { return a.energy - b.energy || a.bpm - b.bpm; },
      'energy-desc': function (a, b) { return b.energy - a.energy || a.bpm - b.bpm; },
      camelot: function (a, b) {
        var A = DJ.cam.parse(DJ.camOf(a)) || { n: 99, l: 'Z' }, B = DJ.cam.parse(DJ.camOf(b)) || { n: 99, l: 'Z' };
        return A.n - B.n || (A.l < B.l ? -1 : A.l > B.l ? 1 : 0) || a.bpm - b.bpm;
      },
      title: function (a, b) { return String(a.title).localeCompare(String(b.title)); },
      duration: function (a, b) { return (a.duration_sec || a.target_minutes * 60 || 0) - (b.duration_sec || b.target_minutes * 60 || 0); }
    };
    var current = [];
    function update() {
      var list = pool().filter(matches);
      var s = SORTS[st.sort];
      if (s) { list = list.slice().sort(s); list.sort(function (a, b) { return (DJ.playable(b) ? 1 : 0) - (DJ.playable(a) ? 1 : 0); }); }
      current = list;
      bpmOut.textContent = st.bpm[0] + '–' + st.bpm[1];
      enOut.textContent = st.energy[0] + '–' + st.energy[1];
      render(list);
      var n = activeCount();
      var dot = DJ.$('[data-filter-count]');
      if (dot) { dot.hidden = !n; dot.textContent = n; }
    }
    function activeCount() {
      return st.fam.size + st.genre.size + st.cam.size + st.role.size + (st.bpm[0] !== BMIN || st.bpm[1] !== BMAX ? 1 : 0) + (st.energy[0] !== 1 || st.energy[1] !== 10 ? 1 : 0) + (st.q ? 1 : 0);
    }
    function queueFn() { return current.filter(DJ.playable); }

    function render(list) {
      grid.classList.toggle('is-list', st.view === 'list');
      grid.innerHTML = '';
      if (!list.length) {
        grid.innerHTML = '<div class="empty card" style="grid-column:1/-1">' + I('search', 'empty-icon') + '<h2>' + (pool().length ? 'לא נמצאו טראקים' : 'הספרייה עוד בבנייה') + '</h2><p>' +
          (pool().length ? 'נסו להרחיב את טווח ה-BPM, להוריד סינון או לחפש משהו אחר.' : 'המפיקים שלנו מרנדרים את הטראקים ממש עכשיו. ' + (soonList.length ? 'סמנו "להציג גם טראקים בדרך" כדי לראות מה מתוכנן.' : '')) + '</p>' +
          (activeCount() ? '<p><button type="button" class="btn btn--ghost btn--sm" data-empty-clear>ניקוי סינונים</button></p>' : '') + '</div>';
        var b = grid.querySelector('[data-empty-clear]'); if (b) b.addEventListener('click', clearAll);
      } else {
        var frag = document.createDocumentFragment();
        list.forEach(function (t) { var c = DJ.trackCard(t, { queue: queueFn }); c._sync(); frag.appendChild(c); });
        grid.appendChild(frag);
      }
      var readyShown = list.filter(DJ.playable).length;
      countEl.innerHTML = 'מציג <b>' + list.length + '</b> מתוך ' + pool().length + ' טראקים' +
        (soonList.length && !st.soon ? ' · <span class="muted">' + soonList.length + ' נוספים ברינדור</span>' : '');
      // actions
      actions.innerHTML = '';
      if (readyShown) {
        var pa = DJ.h('<button type="button" class="btn btn--ghost btn--sm">' + I('play') + '<span>ניגון הכל (' + readyShown + ')</span></button>');
        pa.addEventListener('click', function () { var q = queueFn(); if (q.length) DJ.player.play(q[0], { queue: q }); });
        actions.appendChild(pa);
        var label = st.genre.size === 1 ? Array.from(st.genre)[0] : st.fam.size === 1 ? DJ.FAMILIES[Array.from(st.fam)[0]] : null;
        if (label || readyShown <= 12) {
          var zb = DJ.h('<button type="button" class="btn btn--ghost btn--sm" title="ZIP עם MP3, JSON ועטיפות - באותו מבנה תיקיות כמו בריפו">' + I('download') + '<span>חבילת ZIP' + (label ? ': ' + esc(label) : '') + '</span></button>');
          zb.addEventListener('click', function () { downloadPack(queueFn(), label || 'selection', zb); });
          actions.appendChild(zb);
        }
      }
    }

    /* ---------------- genre pack (JSZip, lazy) ---------------- */
    function slugify(s) { return String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'pack'; }
    function downloadPack(list, label, btn) {
      if (DJ.isFile) { DJ.toast('הורדת ZIP עובדת רק דרך שרת (python -m http.server) או באתר עצמו.'); return; }
      if (!list.length) return;
      var total = list.reduce(function (s, t) { return s + (t.size_bytes || 10e6); }, 0);
      if (total > 220e6 && !window.confirm('החבילה גדולה (' + Math.round(total / 1e6) + ' MB). להמשיך?')) return;
      btn.disabled = true;
      var span = btn.querySelector('span'), orig = span.textContent;
      DJ.loadScript('https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js').then(function () {
        var zip = new window.JSZip(), done = 0;
        var jobs = [];
        list.forEach(function (t) {
          var files = [t.file, t.file.replace(/\.[^.]+$/, '.json')];
          if (t.cover) files.push(t.cover);
          files.forEach(function (f) {
            jobs.push(fetch(DJ.media(f)).then(function (r) { if (!r.ok) throw new Error(f); return r.arrayBuffer(); }).then(function (buf) {
              zip.file('DJ-Lab/' + f, buf);
            }).catch(function () { /* optional file missing */ }).then(function () {
              done++; span.textContent = 'מוריד… ' + Math.round(100 * done / jobs.length) + '%';
            }));
          });
        });
        return Promise.all(jobs).then(function () {
          zip.file('DJ-Lab/README.txt', 'DJ Lab Originals - CC0 1.0\r\nExtract this folder (keep the structure) and use the Rekordbox XML generator on the site with the path to DJ-Lab\\music.\r\n');
          span.textContent = 'אורז…';
          return zip.generateAsync({ type: 'blob', compression: 'STORE' });
        }).then(function (blob) {
          var a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'djlab-' + slugify(label) + '.zip';
          document.body.appendChild(a); a.click(); setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 2000);
          DJ.toast('החבילה ירדה. חלצו אותה ושמרו על מבנה התיקיות.');
        });
      }).catch(function (e) { console.error(e); DJ.toast('ההורדה נכשלה. נסו שוב או הורידו טראקים בודדים.'); })
        .then(function () { btn.disabled = false; span.textContent = orig; });
    }

    /* ---------------- toolbar ---------------- */
    var search = DJ.$('[data-lib-search]');
    search.value = st.q;
    search.addEventListener('input', DJ.debounce(function () { st.q = search.value.trim(); update(); }, 120));
    var sortSel = DJ.$('[data-lib-sort]');
    sortSel.value = SORTS.hasOwnProperty(st.sort) ? st.sort : 'default';
    sortSel.addEventListener('change', function () { st.sort = sortSel.value; DJ.store.set('lib-sort', st.sort); update(); });
    DJ.$$('[data-view]').forEach(function (b) {
      b.setAttribute('aria-pressed', String(b.getAttribute('data-view') === st.view));
      b.addEventListener('click', function () {
        st.view = b.getAttribute('data-view'); DJ.store.set('lib-view', st.view);
        DJ.$$('[data-view]').forEach(function (x) { x.setAttribute('aria-pressed', String(x === b)); });
        render(current);
      });
    });
    var ft = DJ.$('[data-filters-toggle]');
    ft.addEventListener('click', function () {
      var open = !aside.classList.contains('is-open');
      aside.classList.toggle('is-open', open); ft.setAttribute('aria-expanded', String(open));
    });

    buildFilters();
    update();
    DJ.player.on(function (k) { if (k !== 'tick') DJ.$$('.track-card', grid).forEach(function (c) { c._sync && c._sync(); }); });
    if (P.get('track')) setTimeout(function () { DJ.openTrack(P.get('track'), { force: true }); }, 50);
  });
})();
