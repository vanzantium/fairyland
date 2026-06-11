// Fairyland Service Worker — offline-first shell caching

const CACHE_NAME = "fairyland-v2";
const SHELL_ASSETS = [
  "/",
  "/canvas",
  "/peek",
  "/static/style.css",
  "/static/app.js",
  "/static/canvas.css",
  "/static/canvas.js",
  "/static/peek.css",
  "/static/peek.js",
  "/static/manifest.json",
  "/static/icon-192.png",
  "/static/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // API calls always go to network
  if (
    url.pathname.startsWith("/step") ||
    url.pathname.startsWith("/rhythm") ||
    url.pathname.startsWith("/session") ||
    url.pathname.startsWith("/weather") ||
    url.pathname.startsWith("/burn") ||
    url.pathname.startsWith("/dwell") ||
    url.pathname.startsWith("/beacon") ||
    url.pathname.startsWith("/shuffle") ||
    url.pathname.startsWith("/drift") ||
    url.pathname.startsWith("/handshake") ||
    url.pathname.startsWith("/plant") ||
    url.pathname.startsWith("/bridge")
  ) {
    event.respondWith(fetch(event.request));
    return;
  }

  // Shell assets: cache-first
  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});
