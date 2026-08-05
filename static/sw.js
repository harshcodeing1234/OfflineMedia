const CACHE_NAME = 'offline-media-cache-v1';
const ASSETS_TO_CACHE = [
  '/',
  '/play',
  '/saved',
  '/dashboard',
  '/history',
  '/scrapp',
  '/manifest.json',
  '/icon.svg',
  'https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:wght@300;400;500&display=swap'
];

// Install Service Worker and cache essential pages
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log('[Service Worker] Caching app shell');
      return cache.addAll(ASSETS_TO_CACHE);
    }).then(() => self.skipWaiting())
  );
});

// Activate and clean up old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cache) => {
          if (cache !== CACHE_NAME) {
            console.log('[Service Worker] Clearing old cache:', cache);
            return caches.delete(cache);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch events: Network First, Fallback to Cache
self.addEventListener('fetch', (event) => {
  const requestUrl = new URL(event.request.url);

  // We do NOT want to cache video files or APIs in the browser cache,
  // as video files are managed via IndexedDB and APIs need real-time data or custom logic.
  if (requestUrl.pathname.startsWith('/cache/') || requestUrl.pathname.startsWith('/api/')) {
    event.respondWith(fetch(event.request));
    return;
  }

  // Network-First with Cache Fallback for pages
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        // Update cache dynamically with the fresh response
        if (response.status === 200) {
          const responseClone = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseClone);
          });
        }
        return response;
      })
      .catch(() => {
        // Fallback to cache if network/server is down
        return caches.match(event.request).then((cachedResponse) => {
          if (cachedResponse) {
            return cachedResponse;
          }
          // If not in cache and it's a page navigation, return `/play`
          if (event.request.mode === 'navigate') {
            return caches.match('/play');
          }
        });
      })
  );
});
