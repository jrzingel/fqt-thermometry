const CACHE_VERSION = 'v1';
const STATIC_CACHE = `static-${CACHE_VERSION}`;
const API_CACHE = `api-${CACHE_VERSION}`;

const STATIC_ASSETS = [
  '/static/style.css',
  '/static/utils.js',
  '/static/uPlot.iife.min.js',
  '/static/uPlot.min.css',
  '/static/gauge.min.js',
  '/static/apple-touch-icon.png',
  '/static/favicon-96x96.png',
  '/static/favicon.svg',
  '/static/web-app-manifest-192x192.png',
  '/static/web-app-manifest-512x512.png',
  'https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== STATIC_CACHE && key !== API_CACHE)
          .map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // API requests: network-first, fall back to cached response
  if (url.pathname.startsWith('/api/') || url.pathname.endsWith('.json')) {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          const clone = response.clone();
          caches.open(API_CACHE).then((cache) => cache.put(event.request, clone));
          return response;
        })
        .catch(() => caches.match(event.request))
    );
    return;
  }

  // Static assets: cache-first
  if (url.pathname.startsWith('/static/') || url.hostname !== location.hostname) {
    event.respondWith(
      caches.match(event.request).then((cached) => cached || fetch(event.request))
    );
    return;
  }

  // HTML pages: network-first
  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request))
  );
});
