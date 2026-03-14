/**
 * HireFlow Service Worker — Offline support + caching
 */

const CACHE_NAME = 'hireflow-v1';
const OFFLINE_URL = '/offline/';

const PRECACHE_URLS = [
  OFFLINE_URL,
  '/static/frontend/css/app.css',
  '/static/frontend/js/api.js',
  '/static/frontend/js/app.js',
];

// Install — precache essential assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS))
  );
  self.skipWaiting();
});

// Activate — clean old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Fetch — network-first with offline fallback
self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;

  // Skip API requests — never cache API responses
  if (event.request.url.includes('/api/')) return;

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        // Cache successful responses for static assets
        if (response.ok && event.request.url.includes('/static/')) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        }
        return response;
      })
      .catch(() => {
        // Try cache first, then offline page
        return caches.match(event.request).then(
          (cached) => cached || caches.match(OFFLINE_URL)
        );
      })
  );
});
