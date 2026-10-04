/* DJ Lab — crates: index art + interactive crate table (sort, filter, Camelot, verified, buy links). */
(function () {
  'use strict';
  var DJ = window.DJ, I = DJ.icon, esc = DJ.esc;

  function hash(s) { var h = 0; for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0; return Math.abs(h); }
  function artFor(slug) {
    var h = hash(slug), a = h % 360, b = (a + 70 + (h >> 3) % 80) % 360;
    return 'radial-gradient(120% 140% at 85% 0%, hsl(' + a + ' 90% 60% / .95), transparent 60%), radial-gradient(120% 140% at 0% 100%, hsl(' + b + ' 90% 55% / .9), transparent 60%), #0d0c16';
  }

  function crateIndex() {
    DJ.$$('.crate-art[data-seed]').forEach(function (el) { el.style.setProperty('--art', artFor(el.getAttribute('data-seed'))); });
  }

  function links(r) {
    var q = encodeURIComponent((r.artist || '') + ' ' + (r.title || '') + (r.mix && !/original/i.test(r.mix) ? ' ' + r.mix : ''));
    var qq = encodeURIComponent((r.artist || '') + ' ' + (r.title || ''));
    return '<span class="ct-links">' +
      '<a href="https://www.beatport.com/search?q=' + q + '" target="_blank" rel="noopener" title="חיפוש ב-Beatport">Beatport</a>' +
      '<a href="https://bandcamp.com/search?q=' + qq + '" target="_blank" rel="noopener" title="חיפוש ב-Bandcamp">Bandcamp</a>' +
      '<a href="https://open.spotify.com/search/' + qq + '" target="_blank" rel="noopener" title="האזנה ב-Spotify">Spotify</a>' +
      '<a href="https://www.youtube.com/results?search_query=' + qq + '" target="_blank" rel="noopener" title="האזנה ב-YouTube">YouTube</a></span>';
  }
  function vbadge(v) {
    v = String(v || '').toLowerCase();
    if (v === 'yes') return '<span class="vbadge vbadge--yes" title="BPM ו-Key אומתו מול מקור אמין">' + I('check') + 'מאומת</span>';
    if (v === 'partial') return '<span class="vbadge vbadge--partial" title="אומת חלקית">חלקי</span>';
    return '<span class="vbadge vbadge--no" title="לא אומת - בדקו ב-Rekordbox אחרי ניתוח">לא אומת</span>';
  }

  function crateTable(host) {
    var slug = host.getAttribute('data-crate');
    var crate = (window.DJLAB_CRATES || []).filter(function (c) { return c.slug === slug; })[0];
    if (!crate || !crate.tracks || !crate.tracks.length) { host.innerHTML = ''; return; }
    var rows = crate.tracks.map(function (r, i) { var o = Object.assign({}, r); o._i = i + 1; o._cam = DJ.cam.norm(r.camelot) || DJ.cam.fromKey(r.key); o._bpm = parseFloat(r.bpm) || 0; o._en = parseFloat(r.energy) || 0; return o; });
    var st = { q: '', cam: '', compat: true, verified: false, sort: '_i', dir: 1 };
    var cams = Array.from(new Set(rows.map(function (r) { return r._cam; }).filter(Boolean))).sort(function (a, b) { var A = DJ.cam.parse(a), B = DJ.cam.parse(b); return A.n - B.n || (A.l < B.l ? -1 : 1); });
    host.innerHTML =
      '<div class="ct-controls">' +
      '<label class="search-field search-field--sm">' + I('search') + '<span class="sr-only">חיפוש בארגז</span><input type="search" placeholder="חיפוש אמן, שם, לייבל…" data-ct-q></label>' +
      '<label class="select-field select-field--sm"><span class="sr-only">סינון לפי Camelot</span><select data-ct-cam><option value="">כל הסולמות</option>' + cams.map(function (c) { return '<option value="' + c + '">' + c + ' · ' + DJ.cam.keys[c] + '</option>'; }).join('') + '</select></label>' +
      '<label class="switch"><input type="checkbox" checked data-ct-compat><span></span>כולל תואמים</label>' +
      '<label class="switch"><input type="checkbox" data-ct-ver><span></span>רק מאומתים</label>' +
      '</div><p class="muted small" data-ct-count></p>' +
      '<div class="table-wrap ct-wrap"><table class="data-table ct-table"><thead><tr>' +
      th('_i', '#') + th('artist', 'אמן') + th('title', 'שם') + '<th class="ct-hide-sm">לייבל</th>' + th('year', 'שנה', 'ct-hide-sm') + th('_bpm', 'BPM') + th('_cam', 'Key') + th('_en', 'אנרגיה', 'ct-hide-sm') + '<th class="ct-hide-sm">תפקיד</th><th>אימות</th><th>הערות</th><th>קנייה / האזנה</th>' +
      '</tr></thead><tbody></tbody></table></div>';
    function th(k, label, cls) { return '<th' + (cls ? ' class="' + cls + '"' : '') + ' aria-sort="none" data-k="' + k + '"><button type="button">' + label + '</button></th>'; }
    var tbody = host.querySelector('tbody');
    function render() {
      var allowed = null;
      if (st.cam) { allowed = new Set([st.cam]); if (st.compat) DJ.cam.compatible(st.cam).forEach(function (x) { allowed.add(x.code); }); }
      var q = st.q.toLowerCase();
      var list = rows.filter(function (r) {
        if (allowed && !allowed.has(r._cam)) return false;
        if (st.verified && String(r.verified).toLowerCase() !== 'yes') return false;
        if (q && [r.artist, r.title, r.mix, r.label, r.notes_he, r.camelot, r.key].join(' ').toLowerCase().indexOf(q) < 0) return false;
        return true;
      });
      list.sort(function (a, b) {
        var A = a[st.sort], B = b[st.sort];
        if (st.sort === '_cam') { var pa = DJ.cam.parse(A) || { n: 99, l: 'Z' }, pb = DJ.cam.parse(B) || { n: 99, l: 'Z' }; return st.dir * (pa.n - pb.n || (pa.l < pb.l ? -1 : pa.l > pb.l ? 1 : 0)); }
        if (typeof A === 'number' || /^\d+(\.\d+)?$/.test(A || '')) return st.dir * ((parseFloat(A) || 0) - (parseFloat(B) || 0));
        return st.dir * String(A || '').localeCompare(String(B || ''));
      });
      tbody.innerHTML = list.map(function (r) {
        var rel = st.cam && r._cam ? DJ.cam.relation(st.cam, r._cam) : null;
        return '<tr>' +
          '<td data-col="idx" class="ct-num muted">' + r._i + '</td>' +
          '<td data-col="artist"><span class="ct-artist" dir="auto">' + esc(r.artist) + '</span></td>' +
          '<td data-col="title" class="ct-title-cell"><span dir="auto">' + esc(r.title) + '</span>' + (r.mix ? ' <span class="ct-mix">(' + esc(r.mix) + ')</span>' : '') + '</td>' +
          '<td data-col="label" class="ct-hide-sm muted small" dir="auto">' + esc(r.label) + '</td>' +
          '<td data-col="year" class="ct-hide-sm ct-num muted">' + esc(r.year) + '</td>' +
          '<td data-col="bpm" class="ct-num"><b>' + esc(r.bpm) + '</b><span class="ct-show-sm muted"> BPM</span></td>' +
          '<td data-col="cam">' + (r._cam ? DJ.camBadge(r._cam) : esc(r.key)) + (rel && rel.type !== 'perfect' ? '<div class="why why--' + rel.type + '" style="margin-top:4px;display:inline-block">' + esc(rel.label) + '</div>' : '') + '</td>' +
          '<td data-col="energy" class="ct-hide-sm">' + (r._en ? DJ.energyHTML(r._en) : '') + '</td>' +
          '<td data-col="role" class="ct-hide-sm">' + DJ.roleHTML(r.role) + '</td>' +
          '<td data-col="verified">' + vbadge(r.verified) + '</td>' +
          '<td data-col="notes" class="ct-notes">' + esc(r.notes_he) + '</td>' +
          '<td data-col="links">' + links(r) + '</td></tr>';
      }).join('') || '<tr><td colspan="12" class="muted" style="text-align:center;padding:24px">אין התאמות. נסו לבטל סינון.</td></tr>';
      host.querySelector('[data-ct-count]').textContent = 'מציג ' + list.length + ' מתוך ' + rows.length + ' טראקים' + (st.cam ? ' · סולמות תואמים ל-' + st.cam : '');
    }
    host.querySelector('[data-ct-q]').addEventListener('input', DJ.debounce(function (e) { st.q = e.target.value.trim(); render(); }, 120));
    host.querySelector('[data-ct-cam]').addEventListener('change', function (e) { st.cam = e.target.value; render(); });
    host.querySelector('[data-ct-compat]').addEventListener('change', function (e) { st.compat = e.target.checked; render(); });
    host.querySelector('[data-ct-ver]').addEventListener('change', function (e) { st.verified = e.target.checked; render(); });
    host.querySelectorAll('th[data-k] button').forEach(function (b) {
      b.addEventListener('click', function () {
        var th = b.parentNode, k = th.getAttribute('data-k');
        if (st.sort === k) st.dir *= -1; else { st.sort = k; st.dir = 1; }
        host.querySelectorAll('th[data-k]').forEach(function (x) { x.setAttribute('aria-sort', 'none'); });
        th.setAttribute('aria-sort', st.dir === 1 ? 'ascending' : 'descending');
        render();
      });
    });
    render();
  }

  DJ.ready(function () {
    crateIndex();
    DJ.$$('[data-crate]').forEach(crateTable);
  });
})();
