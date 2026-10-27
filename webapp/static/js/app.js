/* Shared page behaviour: theme, nav, service worker, install prompt, connectivity, outbox sync. */
(function () {
  'use strict';
  const A = window.Arena, $ = id => document.getElementById(id);
  A.applyTheme = t => { document.documentElement.dataset.theme = t; const m = document.querySelector('meta[name=theme-color]'); if (m) m.content = t === 'light' ? '#f2f5fb' : '#0b1220'; };
  A.applyTheme(A.settings.get().theme);
  const page = document.body.dataset.page;
  document.querySelectorAll('#nav a').forEach(a => { if (a.dataset.page === page) a.setAttribute('aria-current', 'page'); });
  $('btn-theme').addEventListener('click', () => {
    const t = document.documentElement.dataset.theme === 'light' ? 'dark' : 'light';
    A.settings.set({ theme: t }); A.applyTheme(t); window.dispatchEvent(new Event('arena:theme'));
  });
  const banner = $('net-banner');
  const net = () => { banner.hidden = navigator.onLine !== false; };
  window.addEventListener('online', () => { net(); A.api.flushOutbox(); }); window.addEventListener('offline', net); net();
  A.api.flushOutbox();

  let deferred = null; const btn = $('btn-install');
  window.addEventListener('beforeinstallprompt', e => { e.preventDefault(); deferred = e; btn.hidden = false; });
  btn.addEventListener('click', async () => { if (!deferred) return; deferred.prompt(); await deferred.userChoice; deferred = null; btn.hidden = true; });
  window.addEventListener('appinstalled', () => { btn.hidden = true; });

  if ('serviceWorker' in navigator && (location.protocol === 'https:' || location.hostname === 'localhost' || location.hostname === '127.0.0.1')) {
    window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(() => { /* PWA is optional */ }));
  }
  A.$ = $;
  A.el = (tag, props, ...kids) => { const e = document.createElement(tag); Object.assign(e, props || {}); kids.flat().forEach(k => e.append(k == null ? '' : k)); return e; };
})();
