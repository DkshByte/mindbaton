// Mindbaton's service worker: only here so the page can be installed as an app (and appear in Android's Share menu).
// It caches nothing and answers nothing: every request — /api/*, sign-in, memory — goes straight to the server,
// so a signed-out browser never sees someone's memory from a cache.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", () => {});
