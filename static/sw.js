const CACHE_NAME = 'marroquineria-marcani-v1';
const ASSETS_TO_CACHE = [
  '/',
  '/static/manifest.json',
  // Añade aquí tus hojas de estilo CSS o JS comunes si tienes, por ejemplo:
  // '/static/css/style.css'
];

// Instalar el Service Worker y guardar en caché el "esqueleto" de la app
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS_TO_CACHE);
    })
  );
});

// Estrategia de caché: Network First (Red primero, si falla va a la Caché)
// Es ideal para sistemas de gestión donde los datos cambian seguido.
self.addEventListener('fetch', (event) => {
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        // Si la respuesta es válida, guardamos una copia en caché
        if (event.request.method === 'GET' && response.status === 200) {
          const responseClone = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseClone);
          });
        }
        return response;
      })
      .catch(() => {
        // Si no hay internet, busca en la caché
        return caches.match(event.request);
      })
  );
});