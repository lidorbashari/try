/* DJ Lab — course index progress + chapter reading experience. */
(function () {
  'use strict';
  var DJ = window.DJ;
  function getRead() { var r = DJ.store.get('guide-read', []); return Array.isArray(r) ? r : []; }
  function setRead(list) { DJ.store.set('guide-read', list); }

  function indexPage() {
    var list = DJ.$('[data-guide-list]');
    if (!list) return;
    var chapters = (window.DJLAB_GUIDE || []).filter(function (c) { return !c.appendix; });
    function paint() {
      var read = getRead(), done = 0, next = null;
      DJ.$$('.ch-row', list).forEach(function (row) {
        var f = row.getAttribute('data-chapter'), is = read.indexOf(f) >= 0;
        row.classList.toggle('is-read', is);
        row.classList.remove('is-next');
        var sr = row.querySelector('[data-sr-read]'); if (sr) sr.textContent = is ? '(נקרא)' : '';
        if (is) done++; else if (!next) next = row;
      });
      if (next && done) next.classList.add('is-next');
      var total = chapters.length || DJ.$$('.ch-row', list).length;
      var pct = total ? Math.round(100 * done / total) : 0;
      var fill = DJ.$('[data-gp-fill]'); if (fill) fill.style.strokeDashoffset = String(326.7 * (1 - pct / 100));
      var p = DJ.$('[data-gp-pct]'); if (p) p.textContent = pct + '%';
      var d = DJ.$('[data-gp-done]'); if (d) d.textContent = done;
      var cont = DJ.$('[data-continue]');
      if (cont) {
        var target = next ? next.querySelector('a').getAttribute('href') : null;
        var last = DJ.store.get('guide-last', null);
        if (done && target) { cont.setAttribute('href', target); cont.querySelector('span').textContent = 'להמשיך מאיפה שעצרתי'; }
        else if (!done && last) { cont.setAttribute('href', last + '.html'); cont.querySelector('span').textContent = 'להמשיך לקרוא'; }
        else if (!target && done) { cont.querySelector('span').textContent = 'סיימתם את כל הקורס! לחזור להתחלה'; }
      }
    }
    var reset = DJ.$('[data-reset-progress]');
    if (reset) reset.addEventListener('click', function () { if (window.confirm('לאפס את ההתקדמות בקורס?')) { setRead([]); DJ.store.del('guide-last'); paint(); } });
    paint();
  }

  function chapterPage() {
    var art = DJ.$('[data-chapter]');
    if (!art || !art.matches('article')) return;
    var file = art.getAttribute('data-chapter');
    DJ.store.set('guide-last', file);
    var bar = DJ.$('[data-reading-bar]'), prose = DJ.$('[data-prose]');
    var btn = DJ.$('[data-mark-read]'), state = DJ.$('[data-read-state]');
    function isRead() { return getRead().indexOf(file) >= 0; }
    function paintRead() {
      var r = isRead();
      if (state) state.hidden = !r;
      if (btn) {
        btn.classList.toggle('is-done', r);
        btn.querySelector('span').textContent = r ? 'נקרא ✓ (לחצו לביטול)' : 'סימון הפרק כנקרא';
      }
    }
    function mark(v) {
      var list = getRead().filter(function (x) { return x !== file; });
      if (v) list.push(file);
      setRead(list); paintRead();
    }
    if (btn) btn.addEventListener('click', function () { mark(!isRead()); if (isRead()) DJ.toast('כל הכבוד! הפרק סומן כנקרא.'); });
    paintRead();

    var autoMarked = false, ticking = false;
    function onScroll() {
      ticking = false;
      if (!prose) return;
      var r = prose.getBoundingClientRect(), vh = window.innerHeight;
      var total = r.height - vh * 0.6, seen = DJ.clamp(-r.top + vh * 0.3, 0, Math.max(1, total));
      var p = DJ.clamp(seen / Math.max(1, total), 0, 1);
      if (bar) bar.style.transform = 'scaleX(' + p.toFixed(4) + ')';
      if (p > 0.97 && !autoMarked && !isRead()) { autoMarked = true; mark(true); }
    }
    window.addEventListener('scroll', function () { if (!ticking) { ticking = true; requestAnimationFrame(onScroll); } }, { passive: true });
    window.addEventListener('resize', onScroll);
    onScroll();

    // TOC: collapse on small screens, highlight current section
    var det = DJ.$('[data-toc-details]');
    if (det && window.matchMedia('(max-width: 1000px)').matches) det.removeAttribute('open');
    var links = DJ.$$('[data-toc-link]');
    if (links.length && 'IntersectionObserver' in window) {
      var map = new Map();
      links.forEach(function (a) { var id = decodeURIComponent(a.getAttribute('href').slice(1)); var h = document.getElementById(id); if (h) map.set(h, a); });
      var active = null;
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (e) {
          if (e.isIntersecting) {
            if (active) active.classList.remove('is-active');
            active = map.get(e.target); if (active) { active.classList.add('is-active'); }
          }
        });
      }, { rootMargin: '-15% 0px -70% 0px' });
      map.forEach(function (_, h) { io.observe(h); });
      links.forEach(function (a) { a.addEventListener('click', function () { if (det && window.matchMedia('(max-width: 1000px)').matches) det.removeAttribute('open'); }); });
    }
  }

  DJ.ready(function () { indexPage(); chapterPage(); });
})();
