/// <reference lib="webworker" />
declare const self: ServiceWorkerGlobalScope;

// Skip waiting and claim clients immediately on install
self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

export {};
