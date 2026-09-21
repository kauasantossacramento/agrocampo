/* Silvinha — chat da assistente virtual.
 *
 * Sem framework: um botão, uma janela, um fetch. O histórico vive em
 * sessionStorage para a conversa sobreviver à navegação entre produtos
 * (a pessoa pergunta na home, abre o produto e continua de onde parou).
 */
(function () {
  const raiz = document.getElementById('silvinha');
  if (!raiz) return;

  const url = raiz.dataset.url;
  const produto = raiz.dataset.produto || '';
  const botao = raiz.querySelector('[data-silvinha-abrir]');
  const janela = raiz.querySelector('#silvinha-janela');
  const fechar = raiz.querySelector('[data-silvinha-fechar]');
  const lista = raiz.querySelector('[data-silvinha-mensagens]');
  const form = raiz.querySelector('[data-silvinha-form]');
  const campo = form.querySelector('input');
  const CHAVE = 'silvinha:historico';

  let historico = [];
  try { historico = JSON.parse(sessionStorage.getItem(CHAVE) || '[]'); } catch (e) { historico = []; }

  function csrf() {
    const m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? m[1] : '';
  }

  function guardar() {
    try { sessionStorage.setItem(CHAVE, JSON.stringify(historico.slice(-12))); } catch (e) {}
  }

  // links no texto viram <a>; o resto é texto puro (nada de HTML do modelo)
  function render(texto) {
    const esc = texto.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    return esc
      .replace(/(https?:\/\/[^\s)]+)/g, '<a href="$1">$1</a>')
      .replace(/\*([^*\n]+)\*/g, '<strong>$1</strong>')
      .replace(/\n/g, '<br>');
  }

  function adicionar(papel, texto, pendente) {
    const el = document.createElement('div');
    el.className = 'silvinha__msg ' + (papel === 'usuario' ? 'silvinha__msg--eu' : 'silvinha__msg--ela');
    if (pendente) { el.classList.add('is-pensando'); el.innerHTML = '<span></span><span></span><span></span>'; }
    else el.innerHTML = render(texto);
    lista.appendChild(el);
    lista.scrollTop = lista.scrollHeight;
    return el;
  }

  // reidrata a conversa anterior
  historico.forEach(m => adicionar(m.papel, m.texto));

  function abrir() {
    janela.hidden = false;
    botao.setAttribute('aria-expanded', 'true');
    raiz.classList.add('is-aberta');
    setTimeout(() => campo.focus(), 50);
  }
  function fecharJanela() {
    janela.hidden = true;
    botao.setAttribute('aria-expanded', 'false');
    raiz.classList.remove('is-aberta');
  }
  botao.addEventListener('click', () => janela.hidden ? abrir() : fecharJanela());
  fechar.addEventListener('click', fecharJanela);
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && !janela.hidden) fecharJanela(); });

  let ocupado = false;
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const pergunta = campo.value.trim();
    if (!pergunta || ocupado) return;
    ocupado = true;
    campo.value = '';
    adicionar('usuario', pergunta);
    const espera = adicionar('assistente', '', true);

    try {
      const r = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
        body: JSON.stringify({ pergunta, historico: historico.slice(-8), produto }),
      });
      const dados = await r.json().catch(() => ({}));
      const texto = dados.texto || dados.erro || 'Não consegui responder agora. Tente de novo em instantes.';
      espera.classList.remove('is-pensando');
      espera.innerHTML = render(texto);
      historico.push({ papel: 'usuario', texto: pergunta }, { papel: 'assistente', texto });
      guardar();
    } catch (err) {
      espera.classList.remove('is-pensando');
      espera.textContent = 'Sem conexão agora. Tente de novo em instantes.';
    } finally {
      ocupado = false;
      lista.scrollTop = lista.scrollHeight;
      campo.focus();
    }
  });
})();
