/* DJ Lab — practice drills & transition demos. Planned items without audio render as "coming soon". */
(function () {
  'use strict';
  var DJ = window.DJ, I = DJ.icon, esc = DJ.esc;

  // which file to load on deck B when a drill is opened in the mix trainer
  var PARTNER = {
    'practice-01': 'practice-03', 'practice-02': 'practice-03', 'practice-03': 'practice-04', 'practice-04': 'practice-03',
    'practice-05': 'practice-04', 'practice-06': 'practice-03', 'practice-07': 'practice-03', 'practice-08': 'practice-09',
    'practice-09': 'practice-08', 'practice-10': 'practice-12', 'practice-11': 'practice-10', 'practice-12': 'practice-10',
    'practice-13': 'practice-03', 'practice-14': 'practice-03', 'practice-15': 'practice-03'
  };

  function steps(v) {
    if (!v) return [];
    if (Array.isArray(v)) return v.map(String).filter(Boolean);
    var lines = String(v).split(/\r?\n+/).map(function (s) { return s.replace(/^\s*(?:\d+[.)]|[-*•])\s*/, '').trim(); }).filter(Boolean);
    return lines;
  }
  function merge(plan, items) {
    var byId = new Map(items.map(function (t) { return [t.id, t]; }));
    var out = plan.map(function (p) { var c = byId.get(p.id); byId.delete(p.id); return c ? Object.assign({}, p, c) : Object.assign({ has_audio: false }, p); });
    byId.forEach(function (t) { out.push(t); });
    return out;
  }
  function badges(t) {
    var cam = DJ.camOf(t);
    return '<div class="pr-badges">' + (t.bpm ? '<span class="badge" dir="ltr">' + DJ.fmtBpm(t.bpm) + ' BPM</span>' : '') +
      (cam ? DJ.camBadge(cam) : '') + (t.duration_sec ? '<span class="badge num">' + DJ.fmtTime(t.duration_sec) + '</span>' : '') +
      (DJ.playable(t) ? '' : '<span class="badge badge--soon">בקרוב</span>') + '</div>';
  }
  function mini(t) {
    var r = DJ.lookup(t);
    var tr = DJ.byId.get(t) || r;
    if (!r) return '<span class="pr-tr"><span class="t">' + esc(t) + '</span></span>';
    return '<a class="pr-tr" href="' + DJ.page('library.html?track=' + encodeURIComponent(t)) + '" title="' + esc(r.title_he || '') + '"><span class="ci-art">' + DJ.coverHTML(tr) + '</span><span class="t">' + esc(r.title || t) + '</span></a>';
  }

  DJ.ready(function () {
    var dHost = DJ.$('[data-practice-list]'), tHost = DJ.$('[data-transition-list]');
    if (!dHost) return;
    var plan = DJ.catalog.plan || {};
    var drills = merge(plan.practice || [], DJ.catalog.practice);
    var trans = merge(plan.transitions || [], DJ.catalog.transitions);
    var dq = function () { return drills.filter(DJ.playable); };
    var tq = function () { return trans.filter(DJ.playable); };

    if (!drills.length) dHost.innerHTML = '<div class="empty card">' + I('practice', 'empty-icon') + '<h2>התרגילים בדרך</h2><p>קבצי התרגול יופיעו כאן אחרי הרינדור.</p></div>';
    drills.forEach(function (t) {
      var st = steps(t.exercise_he);
      var num = (t.id || '').replace(/^\D+-?/, '');
      var el = DJ.h('<article class="card pr-card' + (DJ.playable(t) ? '' : ' is-soon') + '" id="' + esc(t.id) + '">' +
        '<div class="pr-head"><span class="pr-id" aria-hidden="true">' + esc(num) + '</span><div><h3 class="pr-title">' + esc(t.title_he || t.title) + '</h3><div class="pr-en">' + esc(t.title || '') + '</div></div></div>' +
        badges(t) +
        '<p class="pr-purpose">' + esc(t.description_he || t.purpose_he || '') + '</p>' +
        '<span class="mp" data-mp></span>' +
        (st.length ? '<details open><summary>' + I('chev-down') + 'איך מתרגלים</summary><ol class="pr-steps">' + st.map(function (s) { return '<li>' + esc(s) + '</li>'; }).join('') + '</ol></details>' : '') +
        '<div class="btn-row">' + (DJ.playable(t) ? '<a class="btn btn--ghost btn--sm" href="' + DJ.page('tools/mix-trainer.html?a=' + encodeURIComponent(t.id) + (PARTNER[t.id] ? '&b=' + PARTNER[t.id] : '')) + '">' + I('mixer') + '<span>לתרגל במאמן</span></a>' : '') + '</div>' +
        '</article>');
      dHost.appendChild(el);
      DJ.miniPlayer(el.querySelector('[data-mp]'), t, { title: 'האזנה', queue: dq });
    });

    if (!trans.length) tHost.innerHTML = '<div class="empty card">' + I('repeat', 'empty-icon') + '<h2>המעברים בדרך</h2><p>מעברי הדוגמה יופיעו כאן אחרי הרינדור.</p></div>';
    trans.forEach(function (t) {
      var st = steps(t.steps_he);
      var num = (t.id || '').replace(/^\D+-?/, '');
      var el = DJ.h('<article class="card pr-card' + (DJ.playable(t) ? '' : ' is-soon') + '" id="' + esc(t.id) + '">' +
        '<div class="pr-head"><span class="pr-id" aria-hidden="true">' + esc(num) + '</span><div><h3 class="pr-title">' + esc(t.technique_he || t.title_he || t.title) + '</h3><div class="pr-en">' + esc(t.title || t.technique || '') + '</div></div></div>' +
        '<div class="pr-flow">' + mini(t.from_id) + '<span aria-label="אל">' + I('arrow-left') + '</span>' + mini(t.to_id) + '</div>' +
        badges(t) +
        (t.description_he ? '<p class="pr-purpose">' + esc(t.description_he) + '</p>' : '') +
        '<span class="mp" data-mp></span>' +
        (st.length ? '<details' + (st.length <= 6 ? ' open' : '') + '><summary>' + I('chev-down') + 'השלבים במעבר</summary><ol class="pr-steps">' + st.map(function (s) { return '<li>' + esc(s) + '</li>'; }).join('') + '</ol></details>' : '') +
        (t.exercise_he ? '<aside class="callout callout--exercise" role="note" style="margin:0"><div class="callout-head">' + I('headphones') + '<span>תרגיל</span></div><div class="callout-body"><p>' + esc(steps(t.exercise_he).join(' ')) + '</p></div></aside>' : '') +
        '<div class="btn-row"><a class="btn btn--ghost btn--sm" href="' + DJ.page('tools/mix-trainer.html?a=' + encodeURIComponent(t.from_id || '') + '&b=' + encodeURIComponent(t.to_id || '')) + '">' + I('mixer') + '<span>לנסות בעצמכם במאמן</span></a></div>' +
        '</article>');
      tHost.appendChild(el);
      DJ.miniPlayer(el.querySelector('[data-mp]'), t, { title: 'האזנה למעבר', queue: tq });
    });
    if (location.hash) { var target = document.getElementById(location.hash.slice(1)); if (target) setTimeout(function () { target.scrollIntoView({ block: 'start' }); }, 60); }
  });
})();
