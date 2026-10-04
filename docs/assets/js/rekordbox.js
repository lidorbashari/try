/* DJ Lab — Rekordbox XML generator (DJ_PLAYLISTS 1.0.0) personalised with the user's music folder path. */
(function () {
  'use strict';
  var DJ = window.DJ, I = DJ.icon;
  var SLOT_NUM = { A: 0, B: 1, C: 2, D: 3, E: 4, F: 5, G: 6, H: 7 };
  var FAMILY_EN = { house: 'House', techno: 'Techno', mainstream: 'Mainstream', breadth: 'Breadth' };
  var EXAMPLE = { win: 'C:\\Users\\Name\\Music\\DJ-Lab\\music', mac: '/Users/name/Music/DJ-Lab/music' };

  function x(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&apos;').replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, ''); }
  function rgb(hex) { var m = /^#?([0-9a-f]{6})$/i.exec(hex || ''); if (!m) return null; var n = parseInt(m[1], 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; }
  function normBase(os, p) {
    p = String(p || '').trim().replace(/^["']|["']$/g, '');
    if (!p) p = EXAMPLE[os];
    p = p.replace(/\\/g, '/').replace(/\/+$/, '').replace(/\/{2,}/g, '/');
    if (os === 'win') { p = p.replace(/^\/+/, ''); if (/^[a-z]:/.test(p)) p = p[0].toUpperCase() + p.slice(1); }
    else if (p[0] !== '/') p = '/' + p;
    return p;
  }
  function fileLocation(os, base, file) {
    var rel = String(file).replace(/^music\//, '');
    var full = base + '/' + rel;
    var enc = full.split('/').map(function (seg, i) { return (i === 0 && /^[A-Za-z]:$/.test(seg)) ? seg : encodeURIComponent(seg); }).join('/');
    return os === 'win' ? 'file://localhost/' + enc : 'file://localhost' + enc;
  }
  function validate(os, raw) {
    var p = String(raw || '').trim();
    if (!p) return { level: 'info', msg: 'לא הוקלד נתיב - נשתמש בדוגמה: ' + EXAMPLE[os] };
    if (os === 'win' && !/^[A-Za-z]:[\\/]/.test(p)) return { level: 'warn', msg: 'נתיב Windows מתחיל באות כונן, למשל C:\\Users\\...' };
    if (os === 'mac' && p[0] !== '/') return { level: 'warn', msg: 'נתיב macOS מתחיל ב-/ למשל /Users/name/Music/...' };
    if (!/music[\\/]?$/i.test(p)) return { level: 'warn', msg: 'הנתיב צריך להסתיים בתיקייה music (זו שמכילה את tracks, practice ו-transitions).' };
    return { level: 'ok', msg: 'נראה טוב!' };
  }

  function collect(o) {
    var items = [];
    DJ.catalog.tracks.filter(DJ.playable).forEach(function (t) { items.push({ t: t, group: 'track' }); });
    if (o.practice) DJ.catalog.practice.filter(DJ.playable).forEach(function (t) { items.push({ t: t, group: 'practice' }); });
    if (o.transitions) DJ.catalog.transitions.filter(DJ.playable).forEach(function (t) { items.push({ t: t, group: 'transition' }); });
    items.forEach(function (it, i) { it.id = i + 1; });
    return items;
  }

  function build(os, rawPath, o) {
    var base = normBase(os, rawPath), items = collect(o), today = new Date().toISOString().slice(0, 10);
    var L = ['<?xml version="1.0" encoding="UTF-8"?>', '<DJ_PLAYLISTS Version="1.0.0">', '  <PRODUCT Name="rekordbox" Version="6.0.0" Company="DJ Lab"/>', '  <COLLECTION Entries="' + items.length + '">'];
    items.forEach(function (it) {
      var t = it.t, cam = DJ.camOf(t), bpm = Number(t.bpm || 0);
      var album = it.group === 'practice' ? 'DJ Lab — Practice' : it.group === 'transition' ? 'DJ Lab — Transitions' : 'DJ Lab — ' + (FAMILY_EN[t.family] || 'Originals') + ' Vol. 1';
      var genre = t.genre || (it.group === 'practice' ? 'Practice' : it.group === 'transition' ? 'Transition' : '');
      var tonality = t.key_short || (cam ? DJ.cam.keys[cam] : '');
      var comments = (cam ? 'Camelot ' + cam + ' · ' : '') + (t.energy ? 'Energy ' + t.energy + ' · ' : '') + 'CC0' + (t.title_he ? ' · ' + t.title_he : '');
      var attrs = [
        ['TrackID', it.id], ['Name', t.title || t.id], ['Artist', t.artist || 'DJ Lab Originals'], ['Composer', ''], ['Album', album], ['Grouping', ''],
        ['Genre', genre], ['Kind', 'MP3 File'], ['Size', t.size_bytes || 0], ['TotalTime', Math.round(t.duration_sec || 0)], ['DiscNumber', 0], ['TrackNumber', 0],
        ['Year', 2026], ['AverageBpm', bpm ? bpm.toFixed(2) : '0.00'], ['DateAdded', today], ['BitRate', 320], ['SampleRate', 44100], ['Comments', comments],
        ['PlayCount', 0], ['Rating', 0], ["Location", fileLocation(os, base, t.file)], ['Remixer', ''], ['Tonality', tonality], ['Label', 'DJ Lab'], ['Mix', '']
      ];
      L.push('    <TRACK ' + attrs.map(function (a) { return a[0] + '="' + x(a[1]) + '"'; }).join(' ') + '>');
      if (bpm) L.push('      <TEMPO Inizio="' + Number(t.first_downbeat_sec || 0).toFixed(3) + '" Bpm="' + bpm.toFixed(2) + '" Metro="' + (t.beats_per_bar || 4) + '/4" Battito="1"/>');
      if (o.memory) (t.memory_cues || []).forEach(function (c) { L.push('      <POSITION_MARK Name="' + x(c.name || '') + '" Type="0" Start="' + Number(c.sec || 0).toFixed(3) + '" Num="-1"/>'); });
      if (o.hotcues) (t.cues || []).forEach(function (c) {
        if (!(c.slot in SLOT_NUM)) return;
        var col = rgb(c.color || DJ.CUE_COLORS[c.slot]) || [40, 226, 20];
        L.push('      <POSITION_MARK Name="' + x(c.name || '') + '" Type="0" Start="' + Number(c.sec || 0).toFixed(3) + '" Num="' + SLOT_NUM[c.slot] + '" Red="' + col[0] + '" Green="' + col[1] + '" Blue="' + col[2] + '"/>');
      });
      L.push('    </TRACK>');
    });
    L.push('  </COLLECTION>');
    // playlists
    var tracksOnly = items.filter(function (it) { return it.group === 'track'; });
    var nodes = [];
    function pl(name, list, ind) {
      var s = [ind + '<NODE Name="' + x(name) + '" Type="1" KeyType="0" Entries="' + list.length + '">'];
      list.forEach(function (it) { s.push(ind + '  <TRACK Key="' + it.id + '"/>'); });
      s.push(ind + '</NODE>');
      return s.join('\n');
    }
    function folder(name, children, ind) { return ind + '<NODE Type="0" Name="' + x(name) + '" Count="' + children.length + '">\n' + children.map(function (c) { return c(ind + '  '); }).join('\n') + '\n' + ind + '</NODE>'; }
    if (tracksOnly.length) nodes.push(function (ind) { return pl('DJ Lab — All Tracks', tracksOnly, ind); });
    DJ.FAMILY_ORDER.forEach(function (f) {
      var fam = tracksOnly.filter(function (it) { return it.t.family === f; });
      if (!fam.length) return;
      var label = FAMILY_EN[f];
      if (!o.genres) { nodes.push(function (ind) { return pl(label, fam, ind); }); return; }
      var genres = [];
      fam.forEach(function (it) { if (genres.indexOf(it.t.genre) < 0) genres.push(it.t.genre); });
      nodes.push(function (ind) {
        return folder(label, [function (i2) { return pl('All ' + label, fam, i2); }].concat(genres.map(function (g) {
          return function (i2) { return pl(g, fam.filter(function (it) { return it.t.genre === g; }), i2); };
        })), ind);
      });
    });
    var pr = items.filter(function (it) { return it.group === 'practice'; }), tr = items.filter(function (it) { return it.group === 'transition'; });
    if (pr.length) nodes.push(function (ind) { return pl('Practice', pr, ind); });
    if (tr.length) nodes.push(function (ind) { return pl('Transitions', tr, ind); });
    var mySet = null;
    if (o.myset) {
      var s = DJ.store.get('set-current', null);
      if (s && s.ids && s.ids.length) {
        var byTrack = new Map(items.map(function (it) { return [it.t.id, it]; }));
        var list = s.ids.map(function (id) { return byTrack.get(id); }).filter(Boolean);
        if (list.length) { mySet = { name: s.name || 'My Set', n: list.length }; nodes.push(function (ind) { return pl('My Set — ' + (s.name || 'DJ Lab'), list, ind); }); }
      }
    }
    L.push('  <PLAYLISTS>');
    L.push('    <NODE Type="0" Name="ROOT" Count="1">');
    L.push(folder('DJ Lab', nodes, '      '));
    L.push('    </NODE>');
    L.push('  </PLAYLISTS>');
    L.push('</DJ_PLAYLISTS>');
    return { xml: L.join('\n') + '\n', items: items, base: base, playlists: nodes.length, mySet: mySet, practice: pr.length, transitions: tr.length, tracks: tracksOnly.length };
  }

  DJ.rekordboxXml = build; // exposed for testing

  DJ.ready(function () {
    var form = DJ.$('[data-rbx-form]');
    if (!form) return;
    var pathEl = DJ.$('[data-rbx-path]'), hint = DJ.$('[data-rbx-path-hint]'), sum = DJ.$('[data-rbx-summary]'), prev = DJ.$('[data-rbx-preview]');
    var os = DJ.store.get('rbx-os', /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent) ? 'mac' : 'win');
    form.querySelectorAll('input[name="os"]').forEach(function (r) { r.checked = r.value === os; });
    pathEl.value = DJ.store.get('rbx-path', '');
    var saved = DJ.store.get('rbx-opts', null) || {};
    form.querySelectorAll('[data-rbx-opt]').forEach(function (c) { var k = c.getAttribute('data-rbx-opt'); if (k in saved) c.checked = !!saved[k]; });
    function opts() { var o = {}; form.querySelectorAll('[data-rbx-opt]').forEach(function (c) { o[c.getAttribute('data-rbx-opt')] = c.checked; }); return o; }
    var last = null;
    function run() {
      os = (form.querySelector('input[name="os"]:checked') || {}).value || 'win';
      pathEl.placeholder = EXAMPLE[os];
      DJ.store.set('rbx-os', os); DJ.store.set('rbx-path', pathEl.value.trim()); DJ.store.set('rbx-opts', opts());
      var v = validate(os, pathEl.value);
      last = build(os, pathEl.value, opts());
      var ex = last.items[0] ? fileLocation(os, last.base, last.items[0].t.file) : fileLocation(os, last.base, 'music/tracks/tech_house/house-05-groove-machine.mp3');
      hint.innerHTML = '<span class="rbx-v rbx-v--' + v.level + '">' + DJ.esc(v.msg) + '</span><br>דוגמה ל-Location: <code dir="ltr" class="rbx-loc">' + DJ.esc(ex) + '</code>';
      sum.innerHTML = last.items.length ?
        '<div class="rbx-stats"><div><b>' + last.tracks + '</b><span>טראקים</span></div><div><b>' + last.practice + '</b><span>תרגילים</span></div><div><b>' + last.transitions + '</b><span>מעברים</span></div><div><b>' + last.items.reduce(function (s, it) { return s + (opts().hotcues ? (it.t.cues || []).length : 0); }, 0) + '</b><span>Hot Cues</span></div></div>' +
        (last.mySet ? '<p class="muted small">כולל את הסט "' + DJ.esc(last.mySet.name) + '" (' + last.mySet.n + ' טראקים) מבונה הסטים.</p>' : '')
        : '<div class="callout callout--warn" role="note"><div class="callout-head">' + I('alert') + '<span>אין עדיין קבצים</span></div><div class="callout-body"><p>הטראקים עוד ברינדור, אז ה-XML יהיה ריק. חזרו לכאן כשהספרייה תתמלא.</p></div></div>';
      var lines = last.xml.split('\n');
      prev.textContent = lines.slice(0, 80).join('\n') + (lines.length > 80 ? '\n… (' + (lines.length - 80) + ' שורות נוספות)' : '');
    }
    form.addEventListener('input', run); form.addEventListener('change', run);
    DJ.$('[data-rbx-download]').addEventListener('click', function () {
      run();
      try {
        var doc = new DOMParser().parseFromString(last.xml, 'application/xml');
        if (doc.getElementsByTagName('parsererror').length) throw new Error('parse');
      } catch (e) { DJ.toast('שגיאה ביצירת ה-XML'); return; }
      DJ.downloadText('rekordbox.xml', last.xml, 'application/xml;charset=utf-8');
      DJ.toast('rekordbox.xml ירד. עכשיו: Preferences → Advanced → Database → rekordbox xml');
    });
    DJ.$('[data-rbx-copy]').addEventListener('click', function () { run(); DJ.copy(last.xml).then(function () { DJ.toast('ה-XML הועתק'); }, function () { DJ.toast('ההעתקה נכשלה - השתמשו בהורדה'); }); });
    run();
  });
})();
