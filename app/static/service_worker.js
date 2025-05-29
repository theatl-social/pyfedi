//https://developers.google.com/web/fundamentals/primers/service-workers

var staticFiles = [
  '/static/fonts/feather/feather.ttf',
  '/static/fonts/feather/feather.woff',
  '/bootstrap/static/css/bootstrap.min.css',
];

self.addEventListener('install', function(event) {
  event.waitUntil(
    caches.open('core').then(function (cache) {
      return cache.addAll(staticFiles);
    })
  );
});


self.addEventListener('fetch', function(event) {
  const request = event.request;
  if (request.url.includes('/static/fonts/feather/')) {
    event.respondWith(
      caches.match(request).then(function(response) {
        return response || fetch(request).then(function(fetchResponse) {
          return fetchResponse;
        });
      })
    );
  }
});

self.addEventListener('fetch', function(event) {
  const request = event.request;
  const url = request.url;

  if (url.includes('/static/fonts/feather/') || url.includes('/bootstrap/static/css/bootstrap.min.css')) {
    event.respondWith(
      caches.match(request).then(function (response) {
        return response || fetch(request);
      })
    );
  }
});
