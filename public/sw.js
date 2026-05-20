const CACHE = 'sleepy-v1';
const URLS = ['/', '/static/main.css'];

self.addEventListener('install', function(e) {
    e.waitUntil(caches.open(CACHE).then(function(c) { return c.addAll(URLS); }));
});

self.addEventListener('fetch', function(e) {
    if (e.request.method !== 'GET') return;
    e.respondWith(
        caches.match(e.request).then(function(r) {
            return r || fetch(e.request).then(function(res) {
                if (res.ok && res.type === 'basic' && e.request.url.indexOf('/static/') !== -1) {
                    var clone = res.clone();
                    caches.open(CACHE).then(function(c) { c.put(e.request, clone); });
                }
                return res;
            }).catch(function() {
                return caches.match('/');
            });
        })
    );
});
