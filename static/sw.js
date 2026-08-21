/* Service worker do PWA AgroCampo.
   Estratégia: cache-first para estáticos, network-first para navegação
   (com fallback para a página offline). */
const CACHE = 'agrocampo-v1';
const ESSENCIAIS = [
  '/offline/',
  '/static/css/design-system.css',
  '/static/css/motion.css',
  '/static/css/layout.css',
  '/static/js/app.js',
  '/static/img/logo-agrocampo.png',
];

self.addEventListener('install', (evento) => {
  evento.waitUntil(caches.open(CACHE).then((c) => c.addAll(ESSENCIAIS)));
  self.skipWaiting();
});

self.addEventListener('activate', (evento) => {
  evento.waitUntil(
    caches.keys().then((chaves) =>
      Promise.all(chaves.filter((c) => c !== CACHE).map((c) => caches.delete(c)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (evento) => {
  const req = evento.request;
  if (req.method !== 'GET') return;

  // navegação: rede primeiro, offline como reserva
  if (req.mode === 'navigate') {
    evento.respondWith(fetch(req).catch(() => caches.match('/offline/')));
    return;
  }

  // estáticos: cache primeiro
  if (req.url.includes('/static/') || req.url.includes('/media/')) {
    evento.respondWith(
      caches.match(req).then(
        (cacheado) =>
          cacheado ||
          fetch(req).then((resposta) => {
            const copia = resposta.clone();
            caches.open(CACHE).then((c) => c.put(req, copia));
            return resposta;
          })
      )
    );
  }
});
