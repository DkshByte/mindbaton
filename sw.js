// memgraph's service worker: only here so the page can be installed as an app (and appear in Android's Share menu).
// Nothing is cached — the memory lives on the server and every request goes to it.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", () => {});
