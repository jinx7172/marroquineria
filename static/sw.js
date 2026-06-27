// Versión del caché
const CACHE_NAME = 'marcani-pwa-v1';
// Archivos estáticos a cachear (No cacheamos los HTML dinámicos de Flask)
const urlsToCache = [
  '/static/style.css',
  '/static/icon-192.png',
  '/static/icon-512.png'
];

// Instalación del Service Worker
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('Cache abierto');
        return cache.addAll(urlsToCache);
      })
  );
});

// Estrategia de red primero (Network First)
self.addEventListener('fetch', event => {
  event.respondWith(
    fetch(event.request)
      .then(response => {
        // Si la red es exitosa, clonamos la respuesta y la guardamos en caché para offline
        const responseClone = response.clone();
        caches.open(CACHE_NAME).then(cache => {
          // Solo cacheamos peticiones GET estáticas
          if (event.request.method === 'GET') {
            cache.put(event.request, responseClone);
          }
        });
        return response;
      })
      .catch(() => {
        // Si la red falla, intentamos devolver el recurso desde la caché
        return caches.match(event.request).then(cachedResponse => {
          if (cachedResponse) {
            return cachedResponse;
          }
          // Si no hay nada en caché y la red falló, mostramos un error o redirigimos
          return new Response('Sin conexión a internet', { status: 503, statusText: 'Offline' });
        });
      })
  );
});

// Activación y limpieza de cachés viejos
self.addEventListener('activate', event => {
  const cacheWhitelist = [CACHE_NAME];
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          if (cacheWhitelist.indexOf(cacheName) === -1) {
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
});