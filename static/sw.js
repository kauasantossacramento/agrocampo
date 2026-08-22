/* Service worker do PWA AgroCampo.

   Navegação: rede primeiro, página offline como reserva.
   Estáticos: responde do cache e revalida em segundo plano, para que uma
   correção de CSS chegue na visita seguinte em vez de nunca. Em produção os
   arquivos já vêm com hash no nome, mas quem abre o site em desenvolvimento
   — ou por um caminho sem hash — ficava preso à versão antiga para sempre. */
const VERSAO = 'v2';
const CACHE = `agrocampo-${VERSAO}`;

const ESSENCIAIS = [
  '/offline/',
  '/static/css/design-system.css',
  '/static/css/motion.css',
  '/static/css/layout.css',
  '/static/css/responsive.css',
  '/static/js/app.js',
  '/static/img/logo-agrocampo.png',
];

self.addEventListener('install', (evento) => {
  evento.waitUntil(
    caches.open(CACHE).then((cache) =>
      // um a um, e não com addAll: se um único arquivo faltar, o addAll
      // rejeita e o service worker inteiro deixa de instalar — a loja perde
      // a página offline por causa de uma imagem renomeada
      Promise.all(
        ESSENCIAIS.map((url) =>
          cache.add(url).catch(() => {
            /* falta de um item não impede o resto */
          })
        )
      )
    )
  );
  self.skipWaiting();
});

self.addEventListener('activate', (evento) => {
  evento.waitUntil(
    caches
      .keys()
      .then((chaves) =>
        Promise.all(chaves.filter((c) => c !== CACHE).map((c) => caches.delete(c)))
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (evento) => {
  const req = evento.request;
  if (req.method !== 'GET') return;

  // navegação: rede primeiro, offline como reserva
  if (req.mode === 'navigate') {
    evento.respondWith(fetch(req).catch(() => caches.match('/offline/')));
    return;
  }

  const estatico = req.url.includes('/static/') || req.url.includes('/media/');
  if (!estatico) return;

  evento.respondWith(
    caches.open(CACHE).then((cache) =>
      cache.match(req).then((cacheado) => {
        const daRede = fetch(req)
          .then((resposta) => {
            if (resposta && resposta.ok) cache.put(req, resposta.clone());
            return resposta;
          })
          .catch(() => cacheado);

        // resposta imediata do cache; a rede atualiza para a próxima visita
        return cacheado || daRede;
      })
    )
  );
});
