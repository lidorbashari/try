/* DJ Lab — accessible rotary knob + fader controls (role="slider", pointer drag, wheel, keyboard, dbl-click reset). */
(function () {
  'use strict';
  var DJ = window.DJ, esc = DJ.esc;
  var SWEEP = 270, START = -135;

  function polar(cx, cy, r, deg) { var a = (deg - 90) * Math.PI / 180; return [cx + r * Math.cos(a), cy + r * Math.sin(a)]; }
  function arc(cx, cy, r, a0, a1) {
    if (Math.abs(a1 - a0) < 0.01) return '';
    var s = polar(cx, cy, r, a0), e = polar(cx, cy, r, a1), large = Math.abs(a1 - a0) > 180 ? 1 : 0, sweep = a1 > a0 ? 1 : 0;
    return 'M' + s[0].toFixed(2) + ' ' + s[1].toFixed(2) + ' A' + r + ' ' + r + ' 0 ' + large + ' ' + sweep + ' ' + e[0].toFixed(2) + ' ' + e[1].toFixed(2);
  }

  /** Knob over a normalised value v in [-1, 1] (bipolar) or [0, 1] (unipolar). */
  DJ.Knob = function (o) {
    var self = this;
    this.o = o = Object.assign({ min: -1, max: 1, value: 0, def: 0, step: 0.01, label: '', name: '', color: 'var(--accent-2)', size: 'md', format: function (v) { return v.toFixed(2); } }, o);
    this.v = o.value;
    var el = this.el = DJ.h('<div class="knob knob--' + o.size + '" role="slider" tabindex="0" aria-label="' + esc(o.name || o.label) + '" aria-valuemin="' + o.min + '" aria-valuemax="' + o.max + '" style="--kc:' + o.color + '">' +
      '<svg viewBox="0 0 64 64" aria-hidden="true"><path class="k-track"/><path class="k-val"/><circle class="k-cap" cx="32" cy="32" r="19"/><line class="k-ptr" x1="32" y1="32" x2="32" y2="17"/></svg>' +
      (o.label ? '<span class="k-label">' + esc(o.label) + '</span>' : '') + '<span class="k-out"></span></div>');
    this.track = el.querySelector('.k-track'); this.val = el.querySelector('.k-val'); this.ptr = el.querySelector('.k-ptr'); this.out = el.querySelector('.k-out');
    this.track.setAttribute('d', arc(32, 32, 27, START, START + SWEEP));
    var startY = 0, startV = 0, drag = false;
    el.addEventListener('pointerdown', function (e) { drag = true; startY = e.clientY; startV = self.v; try { el.setPointerCapture(e.pointerId); } catch (x) { /* */ } el.classList.add('is-drag'); e.preventDefault(); el.focus({ preventScroll: true }); });
    el.addEventListener('pointermove', function (e) {
      if (!drag) return;
      var range = o.max - o.min, px = e.shiftKey ? 600 : 160;
      self.set(startV + (startY - e.clientY) / px * range, true);
    });
    var end = function () { drag = false; el.classList.remove('is-drag'); };
    el.addEventListener('pointerup', end); el.addEventListener('pointercancel', end);
    el.addEventListener('dblclick', function () { self.set(o.def, true); });
    el.addEventListener('wheel', function (e) { e.preventDefault(); self.set(self.v - Math.sign(e.deltaY) * (o.max - o.min) / (e.shiftKey ? 200 : 40), true); }, { passive: false });
    el.addEventListener('keydown', function (e) {
      var r = o.max - o.min, d = 0;
      if (e.key === 'ArrowUp' || e.key === 'ArrowRight') d = r / 40;
      else if (e.key === 'ArrowDown' || e.key === 'ArrowLeft') d = -r / 40;
      else if (e.key === 'PageUp') d = r / 8;
      else if (e.key === 'PageDown') d = -r / 8;
      else if (e.key === 'Home') { self.set(o.min, true); e.preventDefault(); return; }
      else if (e.key === 'End') { self.set(o.max, true); e.preventDefault(); return; }
      else if (e.key === '0' || e.key === 'Delete' || e.key === 'Backspace') { self.set(o.def, true); e.preventDefault(); return; }
      else return;
      e.preventDefault(); e.stopPropagation();
      self.set(self.v + d, true);
    });
    this.set(this.v, false);
  };
  DJ.Knob.prototype.set = function (v, fire) {
    var o = this.o;
    v = DJ.clamp(Math.round(v / o.step) * o.step, o.min, o.max);
    if (Math.abs(v - o.def) < o.step * 1.5 && o.snap !== false) v = o.def;
    this.v = v;
    var t = (v - o.min) / (o.max - o.min), ang = START + t * SWEEP;
    var z = (o.def - o.min) / (o.max - o.min), a0 = START + z * SWEEP;
    this.val.setAttribute('d', arc(32, 32, 27, Math.min(a0, ang), Math.max(a0, ang)));
    this.ptr.setAttribute('transform', 'rotate(' + ang.toFixed(1) + ' 32 32)');
    var txt = o.format(v);
    this.out.textContent = txt;
    this.el.setAttribute('aria-valuenow', v.toFixed(2));
    this.el.setAttribute('aria-valuetext', txt);
    this.el.classList.toggle('is-off', v === o.def);
    if (fire && o.onInput) o.onInput(v);
  };

  /** Linear fader (vertical or horizontal). For vertical faders, `invert` puts max at the bottom (tempo-fader style). */
  DJ.Fader = function (o) {
    var self = this;
    this.o = o = Object.assign({ orient: 'v', min: 0, max: 1, value: 0, def: 0, step: 0.01, fine: null, name: '', invert: false, format: function (v) { return v.toFixed(2); }, cls: '' }, o);
    this.v = o.value;
    var el = this.el = DJ.h('<div class="fader fader--' + o.orient + ' ' + o.cls + '" role="slider" tabindex="0" aria-label="' + esc(o.name) + '" aria-orientation="' + (o.orient === 'v' ? 'vertical' : 'horizontal') + '" aria-valuemin="' + o.min + '" aria-valuemax="' + o.max + '">' +
      '<span class="f-slot"></span><span class="f-ticks"></span><span class="f-center"></span><span class="f-thumb"></span></div>');
    this.thumb = el.querySelector('.f-thumb');
    var drag = false, startPos = 0, startV = 0;
    function posFrom(e) {
      var r = el.getBoundingClientRect();
      if (o.orient === 'v') { var t = DJ.clamp((e.clientY - r.top) / r.height, 0, 1); return o.invert ? t : 1 - t; }
      return DJ.clamp((e.clientX - r.left) / r.width, 0, 1);
    }
    el.addEventListener('pointerdown', function (e) {
      drag = true; try { el.setPointerCapture(e.pointerId); } catch (x) { /* */ }
      el.classList.add('is-drag'); e.preventDefault(); el.focus({ preventScroll: true });
      var onThumb = e.target === self.thumb;
      startPos = o.orient === 'v' ? e.clientY : e.clientX; startV = self.v;
      if (!onThumb) self.set(o.min + posFrom(e) * (o.max - o.min), true);
      startV = self.v;
    });
    el.addEventListener('pointermove', function (e) {
      if (!drag) return;
      var r = el.getBoundingClientRect(), len = o.orient === 'v' ? r.height : r.width;
      var dp = ((o.orient === 'v' ? e.clientY : e.clientX) - startPos) / len;
      if (o.orient === 'v' && !o.invert) dp = -dp;
      var k = e.shiftKey ? 0.15 : 1;
      self.set(startV + dp * (o.max - o.min) * k, true);
    });
    var end = function () { drag = false; el.classList.remove('is-drag'); };
    el.addEventListener('pointerup', end); el.addEventListener('pointercancel', end);
    el.addEventListener('dblclick', function () { self.set(o.def, true); });
    el.addEventListener('wheel', function (e) { e.preventDefault(); var s = o.fine || o.step; self.set(self.v + (e.deltaY > 0 ? 1 : -1) * s * (o.orient === 'v' && !o.invert ? -1 : 1) * (e.shiftKey ? 1 : 5), true); }, { passive: false });
    el.addEventListener('keydown', function (e) {
      var s = o.fine || o.step, d = 0;
      var inc = o.orient === 'v' ? (o.invert ? 'ArrowDown' : 'ArrowUp') : 'ArrowRight';
      var dec = o.orient === 'v' ? (o.invert ? 'ArrowUp' : 'ArrowDown') : 'ArrowLeft';
      if (e.key === inc) d = s; else if (e.key === dec) d = -s;
      else if (e.key === 'PageUp') d = (o.max - o.min) / 10; else if (e.key === 'PageDown') d = -(o.max - o.min) / 10;
      else if (e.key === 'Home') { self.set(o.min, true); e.preventDefault(); return; }
      else if (e.key === 'End') { self.set(o.max, true); e.preventDefault(); return; }
      else if (e.key === '0') { self.set(o.def, true); e.preventDefault(); return; }
      else return;
      e.preventDefault(); e.stopPropagation();
      self.set(self.v + d * (e.shiftKey ? 5 : 1), true);
    });
    this.set(this.v, false);
  };
  DJ.Fader.prototype.set = function (v, fire) {
    var o = this.o;
    v = DJ.clamp(Math.round(v / o.step) * o.step, o.min, o.max);
    if (Math.abs(v) < 1e-9) v = 0;
    this.v = v;
    var t = (v - o.min) / (o.max - o.min);
    var p = o.orient === 'v' ? (o.invert ? t : 1 - t) : t;
    this.el.style.setProperty('--p', (p * 100).toFixed(3) + '%');
    var txt = o.format(v);
    this.el.setAttribute('aria-valuenow', String(+v.toFixed(4)));
    this.el.setAttribute('aria-valuetext', txt);
    if (fire && o.onInput) o.onInput(v);
  };
  DJ.Fader.prototype.setRange = function (min, max) { this.o.min = min; this.o.max = max; this.el.setAttribute('aria-valuemin', min); this.el.setAttribute('aria-valuemax', max); this.set(this.v, true); };
})();
