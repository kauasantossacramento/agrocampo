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
  const urlAcao = raiz.dataset.acao;
  let logado = raiz.dataset.logado === '1';
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
    // o token guardado é atualizado após login/cadastro (o Django gira o token)
    if (raiz.dataset.csrfNovo) return raiz.dataset.csrfNovo;
    const m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? m[1] : (raiz.dataset.csrf || '');
  }
  const esc = (t) => String(t == null ? '' : t).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  async function postar(dados) {
    const r = await fetch(urlAcao, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
      body: JSON.stringify(dados),
    });
    const d = await r.json();
    if (d && d.csrf) raiz.dataset.csrfNovo = d.csrf;
    return d;
  }

  /* ---- cartão de compra: a IA propõe, a pessoa confirma num botão ---- */
  function cartaoCompra(acao) {
    const p = acao.produto;
    const el = document.createElement('div');
    el.className = 'silvinha__msg silvinha__msg--ela silvinha__compra';
    let variacoes = '';
    if (p.tem_variacoes && p.variacoes.length) {
      variacoes = '<label class="silvinha__campo"><span>Tamanho</span><select data-compra-variacao>'
        + p.variacoes.map(v => '<option value="' + v.id + '">' + esc(v.rotulo) + ' — ' + esc(v.preco) + '</option>').join('')
        + '</select></label>';
    }
    el.innerHTML =
      '<div class="silvinha__compra-topo">'
      + (p.foto ? '<img src="' + esc(p.foto) + '" alt="">' : '')
      + '<div><strong>' + esc(p.nome) + '</strong><span class="silvinha__compra-preco">' + esc(p.preco) + '</span></div></div>'
      + variacoes
      + '<label class="silvinha__campo"><span>Quantidade</span>'
      + '<span class="silvinha__qtd"><button type="button" data-qtd="-1">−</button><input type="number" min="1" max="50" value="' + acao.quantidade + '" data-compra-qtd><button type="button" data-qtd="1">+</button></span></label>'
      + '<button type="button" class="btn btn--primary silvinha__compra-btn" data-compra-confirmar>Comprar agora</button>'
      + '<div class="silvinha__compra-status xs muted" data-compra-status></div>';
    const qtd = el.querySelector('[data-compra-qtd]');
    el.querySelectorAll('[data-qtd]').forEach(b => b.addEventListener('click', () => {
      qtd.value = Math.max(1, Math.min(50, (parseInt(qtd.value, 10) || 1) + parseInt(b.dataset.qtd, 10)));
    }));
    el.querySelector('[data-compra-confirmar]').addEventListener('click', () => comprar(el, p.slug));
    lista.appendChild(el);
    lista.scrollTop = lista.scrollHeight;
  }

  async function comprar(el, slug) {
    const status = el.querySelector('[data-compra-status]');
    const botao = el.querySelector('[data-compra-confirmar]');
    const variacao = el.querySelector('[data-compra-variacao]');
    const quantidade = parseInt(el.querySelector('[data-compra-qtd]').value, 10) || 1;
    if (!logado) { formularioAcesso(el, () => comprar(el, slug)); return; }
    botao.disabled = true; status.textContent = 'Adicionando…';
    try {
      const d = await postar({ tipo: 'comprar', produto: slug, quantidade, variacao: variacao ? variacao.value : '' });
      if (d.precisa_login) { logado = false; botao.disabled = false; formularioAcesso(el, () => comprar(el, slug)); return; }
      if (!d.ok) { status.textContent = d.erro || 'Não consegui adicionar.'; botao.disabled = false; return; }
      const contador = document.querySelector('[data-cart-count]');
      if (contador) { contador.textContent = d.quantidade_carrinho; contador.hidden = false; }
      status.innerHTML = '<span style="color:var(--green)">' + esc(d.mensagem) + '</span> Indo para a entrega e o pagamento…';
      historico.push({ papel: 'assistente', texto: d.mensagem }); guardar();
      setTimeout(() => { location.href = d.checkout; }, 900);
    } catch (e) {
      status.textContent = 'Sem conexão agora. Tente de novo.'; botao.disabled = false;
    }
  }

  /* ---- acesso dentro do chat: entrar ou criar conta, sem sair da conversa ---- */
  function formularioAcesso(ancora, depois) {
    if (raiz.querySelector('[data-acesso]')) { raiz.querySelector('[data-acesso]').scrollIntoView({ block: 'nearest' }); return; }
    const el = document.createElement('div');
    el.className = 'silvinha__msg silvinha__msg--ela silvinha__acesso';
    el.setAttribute('data-acesso', '');
    el.innerHTML =
      '<p style="margin:0 0 6px"><strong>Para fechar a compra, me diga quem é você.</strong></p>'
      + '<div class="silvinha__abas"><button type="button" class="is-ativa" data-aba="entrar">Já tenho conta</button><button type="button" data-aba="cadastrar">Criar conta</button></div>'
      + '<form data-form="entrar" class="silvinha__form-acesso">'
      + '<input type="email" name="email" placeholder="Seu e-mail" autocomplete="email" required>'
      + '<input type="password" name="senha" placeholder="Sua senha" autocomplete="current-password" required>'
      + '<button type="submit" class="btn btn--primary">Entrar e continuar</button></form>'
      + '<form data-form="cadastrar" class="silvinha__form-acesso" hidden>'
      + '<input type="text" name="nome" placeholder="Seu nome" autocomplete="name" required>'
      + '<input type="email" name="email" placeholder="Seu e-mail" autocomplete="email" required>'
      + '<input type="tel" name="telefone" placeholder="WhatsApp com DDD" autocomplete="tel" required>'
      + '<input type="password" name="senha" placeholder="Crie uma senha (mín. 8)" autocomplete="new-password" minlength="8" required>'
      + '<button type="submit" class="btn btn--primary">Criar conta e continuar</button></form>'
      + '<div class="silvinha__compra-status xs" data-acesso-status></div>';
    const status = el.querySelector('[data-acesso-status]');
    el.querySelectorAll('[data-aba]').forEach(b => b.addEventListener('click', () => {
      el.querySelectorAll('[data-aba]').forEach(x => x.classList.toggle('is-ativa', x === b));
      el.querySelectorAll('[data-form]').forEach(f => { f.hidden = f.dataset.form !== b.dataset.aba; });
      status.textContent = '';
    }));
    el.querySelectorAll('[data-form]').forEach(form => form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const dados = Object.fromEntries(new FormData(form).entries());
      dados.tipo = form.dataset.form;
      const botao = form.querySelector('button[type=submit]');
      botao.disabled = true; status.textContent = 'Um instante…';
      try {
        const d = await postar(dados);
        if (!d.ok) {
          status.style.color = 'var(--red)';
          status.textContent = d.erro || Object.values(d.erros || {}).join(' ') || 'Confira os dados.';
          botao.disabled = false; return;
        }
        logado = true;
        status.style.color = 'var(--green)';
        status.textContent = (d.criado ? 'Conta criada! ' : 'Bem-vindo de volta, ') + esc(d.nome) + (d.criado ? '' : '!');
        el.querySelectorAll('form').forEach(f => { f.hidden = true; });
        el.querySelector('.silvinha__abas').hidden = true;
        if (depois) setTimeout(depois, 400);
      } catch (err) {
        status.textContent = 'Sem conexão agora.'; botao.disabled = false;
      }
    }));
    lista.appendChild(el);
    lista.scrollTop = lista.scrollHeight;
    setTimeout(() => { const i = el.querySelector('form:not([hidden]) input'); if (i) i.focus(); }, 60);
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
      if (dados.acao && dados.acao.tipo === 'comprar') cartaoCompra(dados.acao);
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
