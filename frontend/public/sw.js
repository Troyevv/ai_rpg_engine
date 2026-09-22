// Static shell only. API/SSE/credentials/markdown and saves always use the network.
const CACHE='ai-rpg-shell-__BUILD_ID__';
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(['/','/offline.html','/manifest.webmanifest','/icons/icon-192.png','/icons/icon-512.png']))));
// Wait for all open clients to close before activating an update: never reload an active generation.
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith('ai-rpg-shell-')&&k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',event=>{
 const req=event.request,url=new URL(req.url);
 if(req.method!=='GET'||url.origin!==self.location.origin||url.pathname.startsWith('/api/'))return;
 if(req.mode==='navigate'){
  event.respondWith(fetch(req).catch(async()=>await caches.match('/offline.html')));return;
 }
 if(url.pathname.startsWith('/assets/')||url.pathname.startsWith('/icons/')){
  event.respondWith(caches.open(CACHE).then(async cache=>{const hit=await cache.match(req);if(hit)return hit;const response=await fetch(req);if(response.ok)await cache.put(req,response.clone());return response}));
 }
});
