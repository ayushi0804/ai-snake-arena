/* Service worker. __VERSION__/__PAGES__/__ASSETS__ are filled in by Flask (/sw.js) so the cache
   name changes whenever any static file or template changes: old caches are deleted on activate. */
const VERSION = '__VERSION__';
const CACHE = 'arena-static-' + VERSION;
const PAGES = __PAGES__;
const ASSETS = __ASSETS__;

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll([...PAGES, ...ASSETS, '/manifest.webmanifest'])).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k.startsWith('arena-') && k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const req = e.request, url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== location.origin) return;
  if (url.pathname.startsWith('/api/')) return;             // API is online-only; app code handles failure
  if (url.pathname === '/sw.js') return;
  if (req.mode === 'navigate') {
    e.respondWith(fetch(req).then(res => {
      if (res.ok) { const copy = res.clone(); caches.open(CACHE).then(c => c.put(req, copy)); }
      return res;
    }).catch(() => caches.match(req, { ignoreSearch: true }).then(r => r || caches.match('/offline'))));
    return;
  }
  e.respondWith(caches.match(req).then(hit => {
    const net = fetch(req).then(res => { if (res.ok) { const copy = res.clone(); caches.open(CACHE).then(c => c.put(req, copy)); } return res; }).catch(() => hit);
    return hit || net;                                       // stale-while-revalidate
  }));
});
self.addEventListener('message', e => { if (e.data === 'skipWaiting') self.skipWaiting(); });
