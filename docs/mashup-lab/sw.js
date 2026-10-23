/* Mashup Lab service worker: the app opens fast and works as an installed app (Add to Home Screen).
   Same-origin files only (the page, its data files and icons), network first so a new version shows at once.
   Apple's previews, artwork and search are never cached or stored: they always stream from Apple. */
"use strict";
const V = "mashlab-d6d9bb3256";
const SHELL = ["./", "manifest.webmanifest", "icons/icon-192.png", "icons/icon-512.png", "icons/apple-touch-icon.png", "icons/favicon-64.png"];
self.addEventListener("install", e => { e.waitUntil(caches.open(V).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())); });
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k.indexOf("mashlab-") === 0 && k !== V).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  const req = e.request, u = new URL(req.url);
  if (req.method !== "GET" || u.origin !== self.location.origin) return;          /* Apple audio / artwork / search: network only */
  e.respondWith(fetch(req).then(r => {
    if (r && r.ok && r.type === "basic") { const cp = r.clone(); caches.open(V).then(c => c.put(req, cp)).catch(() => {}); }
    return r;
  }).catch(() => caches.match(req, { ignoreSearch: true }).then(r => r || (req.mode === "navigate" ? caches.match("./") : undefined))
    .then(r => r || new Response("", { status: 504, statusText: "offline" }))));
});
