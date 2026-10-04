/* DJ Lab — example sets: energy sparklines on the index, energy chart + continuous play on set pages. */
(function () {
  'use strict';
  var DJ = window.DJ;
  function tracksOf(csv) { return String(csv || '').split(',').map(function (id) { return DJ.lookup(id.trim()); }).filter(Boolean); }
  DJ.ready(function () {
    DJ.$$('[data-set-spark]').forEach(function (el) {
      var ts = tracksOf(el.getAttribute('data-set-spark'));
      el.innerHTML = ts.length ? DJ.sparkline(ts) : '';
      if (!ts.length) el.style.display = 'none';
    });
    var box = DJ.$('[data-set-tracks]');
    if (box) {
      var ts = tracksOf(box.getAttribute('data-set-tracks'));
      var chart = box.querySelector('[data-energy-chart]');
      var draw = function () { DJ.energyChart(chart, ts, { height: 190 }); };
      draw();
      window.addEventListener('resize', DJ.debounce(draw, 150));
      var pb = box.querySelector('[data-play-set]');
      var playable = ts.filter(DJ.playable);
      if (!playable.length) { pb.disabled = true; pb.querySelector('span').textContent = 'הטראקים בדרך'; }
      pb.addEventListener('click', function () { if (playable.length) DJ.player.play(playable[0], { queue: playable }); });
    }
  });
})();
