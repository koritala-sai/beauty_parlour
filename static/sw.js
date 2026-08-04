const CACHE_NAME = "glow-studio-v3";

// Only cache stable, static assets. Pages like /my-bookings or /admin
// depend on live data, so they're intentionally NOT cached here.
const STATIC_ASSETS = [
    "/static/css/style.css",
    "/static/manifest.json",
    "/static/icons/icon-192.png",
    "/static/icons/icon-512.png",
];

self.addEventListener("install", (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
    );
    self.skipWaiting();
});

self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(
                keys
                    .filter((key) => key !== CACHE_NAME)
                    .map((key) => caches.delete(key))
            )
        )
    );
    self.clients.claim();
});

// Cache-first for static assets, network-first for everything else
// (so booking pages, admin pages, and API calls always get fresh data).
self.addEventListener("fetch", (event) => {
    const { request } = event;

    if (STATIC_ASSETS.some((path) => request.url.endsWith(path))) {
        event.respondWith(
            caches.match(request).then((cached) => cached || fetch(request))
        );
        return;
    }

    event.respondWith(
        fetch(request).catch(() => caches.match(request))
    );
});
