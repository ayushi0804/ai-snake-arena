/* Arena.charts - dependency-free canvas charts (line, grouped bars) that follow the theme. */
(function (root) {
  'use strict';
  const A = root.Arena, reg = new Map();
  const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const PALETTE = ['#3ddc84', '#4da3ff', '#ffc857', '#ff6b81', '#b28dff'];
  function setup(cv) {
    const dpr = root.devicePixelRatio || 1, w = cv.clientWidth || 300, h = cv.clientHeight || 220;
    cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
    const g = cv.getContext('2d'); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, w, h);
    g.font = '12px system-ui, sans-serif'; return { g, w, h };
  }
  const nice = max => { if (max <= 0) return 1; const p = Math.pow(10, Math.floor(Math.log10(max))); const f = max / p; return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p; };
  function frame(g, w, h, top, labels, maxV) {
    const L = 44, R = 10, B = 28, T = top; g.fillStyle = css('--muted'); g.strokeStyle = css('--border'); g.textAlign = 'right';
    for (let i = 0; i <= 4; i++) { const y = T + (h - T - B) * (1 - i / 4); g.beginPath(); g.moveTo(L, y); g.lineTo(w - R, y); g.stroke(); g.fillText(String(+(maxV * i / 4).toFixed(2)), L - 6, y + 4); }
    return { L, R, B, T, pw: w - L - R, ph: h - T - B };
  }
  function legend(g, series, w) { let x = 46; g.textAlign = 'left'; series.forEach((s, i) => { if (series.length < 2) return; g.fillStyle = PALETTE[i % 5]; g.fillRect(x, 4, 10, 10); g.fillStyle = css('--text'); g.fillText(s.name, x + 14, 13); x += 24 + g.measureText(s.name).width; }); }
  function describe(cv, labels, series) { cv.setAttribute('role', 'img'); cv.setAttribute('aria-label', series.map(s => s.name + ': ' + labels.map((l, i) => l + ' ' + (s.values[i] == null ? 'n/a' : s.values[i])).join(', ')).join('. ')); }
  function bars(cv, labels, series) {
    const { g, w, h } = setup(cv); describe(cv, labels, series);
    const vals = series.flatMap(s => s.values).filter(v => v != null); if (!labels.length || !vals.length) { g.fillStyle = css('--muted'); g.textAlign = 'center'; g.fillText('No data', w / 2, h / 2); return; }
    const maxV = nice(Math.max(...vals)), f = frame(g, w, h, series.length > 1 ? 20 : 8, labels, maxV), gw = f.pw / labels.length, bw = Math.min(40, gw * 0.7 / series.length);
    labels.forEach((l, i) => {
      series.forEach((s, j) => { const v = s.values[i]; if (v == null) return; const bh = f.ph * v / maxV, x = f.L + gw * i + (gw - bw * series.length) / 2 + bw * j;
        g.fillStyle = PALETTE[j % 5]; g.fillRect(x, f.T + f.ph - bh, bw - 2, bh); });
      g.fillStyle = css('--muted'); g.textAlign = 'center'; g.fillText(l, f.L + gw * (i + 0.5), h - 10, gw);
    }); legend(g, series, w);
  }
  function line(cv, labels, series) {
    const { g, w, h } = setup(cv); describe(cv, labels, series);
    const vals = series.flatMap(s => s.values).filter(v => v != null); if (!labels.length || !vals.length) { g.fillStyle = css('--muted'); g.textAlign = 'center'; g.fillText('No data', w / 2, h / 2); return; }
    const maxV = nice(Math.max(...vals)), f = frame(g, w, h, series.length > 1 ? 20 : 8, labels, maxV), n = Math.max(1, labels.length - 1);
    series.forEach((s, j) => { g.strokeStyle = g.fillStyle = PALETTE[j % 5]; g.lineWidth = 2; g.beginPath(); let started = false;
      s.values.forEach((v, i) => { if (v == null) return; const x = f.L + (labels.length === 1 ? f.pw / 2 : f.pw * i / n), y = f.T + f.ph * (1 - v / maxV); started ? g.lineTo(x, y) : g.moveTo(x, y); started = true; }); g.stroke();
      s.values.forEach((v, i) => { if (v == null) return; const x = f.L + (labels.length === 1 ? f.pw / 2 : f.pw * i / n), y = f.T + f.ph * (1 - v / maxV); g.beginPath(); g.arc(x, y, 3, 0, 6.3); g.fill(); }); });
    g.fillStyle = css('--muted'); g.textAlign = 'center'; g.fillText(labels[0], f.L, h - 10); if (labels.length > 1) g.fillText(labels[labels.length - 1], w - f.R - 10, h - 10); legend(g, series, w);
  }
  function draw(kind, id, labels, series) { const cv = document.getElementById(id); if (!cv) return; reg.set(id, [kind, labels, series]); (kind === 'line' ? line : bars)(cv, labels, series); }
  const redraw = () => reg.forEach(([k, l, s], id) => { const cv = document.getElementById(id); if (cv) (k === 'line' ? line : bars)(cv, l, s); });
  let t; root.addEventListener('resize', () => { clearTimeout(t); t = setTimeout(redraw, 120); }); root.addEventListener('arena:theme', redraw);
  A.charts = { line: (id, l, s) => draw('line', id, l, s), bars: (id, l, s) => draw('bars', id, l, s), redraw };
})(window);
