/* ============================================================================
   AgroCampo — interações do storefront.
   Sem dependências. Tudo é progressive enhancement: se o JS falhar,
   os formulários continuam funcionando por POST normal.
   ========================================================================== */
(function () {
  'use strict';

  const $  = (sel, ctx = document) => ctx.querySelector(sel);
  const $$ = (sel, ctx = document) => Array.from(ctx.querySelectorAll(sel));
  const reduzido = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ------------------------------------------------------------------ CSRF */
  function csrf() {
    const campo = $('[name=csrfmiddlewaretoken]');
    if (campo) return campo.value;
    const match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? match[1] : '';
  }

  /* ---------------------------------------------------------------- toasts */
  function toast(mensagem, tipo = 'info', duracao = 3800) {
    let pilha = $('.toast-stack');
    if (!pilha) {
      pilha = document.createElement('div');
      pilha.className = 'toast-stack';
      pilha.setAttribute('role', 'status');
      pilha.setAttribute('aria-live', 'polite');
      document.body.appendChild(pilha);
    }

    const el = document.createElement('div');
    el.className = `toast toast--${tipo}`;
    el.innerHTML = `<span>${mensagem}</span>
      <button class="toast__close" aria-label="Fechar">&times;</button>`;
    pilha.appendChild(el);

    const sair = () => {
      el.classList.add('is-leaving');
      el.addEventListener('animationend', () => el.remove(), { once: true });
    };
    el.querySelector('.toast__close').addEventListener('click', sair);
    setTimeout(sair, duracao);
  }
  window.agroToast = toast;

  /* --------------------------------------------------- revelar ao rolar */
  function iniciarReveal() {
    const alvos = $$('[data-reveal], [data-stagger]');
    if (!alvos.length) return;

    if (reduzido || !('IntersectionObserver' in window)) {
      alvos.forEach((el) => el.classList.add('is-visible'));
      return;
    }

    const observador = new IntersectionObserver(
      (entradas) => {
        entradas.forEach((entrada) => {
          if (!entrada.isIntersecting) return;
          entrada.target.classList.add('is-visible');
          observador.unobserve(entrada.target);
        });
      },
      { threshold: 0.12, rootMargin: '0px 0px -60px 0px' }
    );
    alvos.forEach((el) => observador.observe(el));
  }

  /* ------------------------------------------ cabeçalho condensa ao rolar */
  function iniciarHeader() {
    const header = $('.site-header');
    if (!header) return;
    let ticking = false;
    const atualizar = () => {
      header.classList.toggle('is-stuck', window.scrollY > 12);
      ticking = false;
    };
    window.addEventListener(
      'scroll',
      () => {
        if (!ticking) {
          window.requestAnimationFrame(atualizar);
          ticking = true;
        }
      },
      { passive: true }
    );
    atualizar();
  }

  /* ------------------------------------------------------------ dropdowns */
  function iniciarDropdowns() {
    $$('[data-dropdown]').forEach((raiz) => {
      const gatilho = $('[data-dropdown-trigger]', raiz);
      const painel = $('[data-dropdown-panel]', raiz);
      if (!gatilho || !painel) return;

      gatilho.setAttribute('aria-expanded', 'false');
      gatilho.addEventListener('click', (e) => {
        e.stopPropagation();
        const aberto = painel.classList.toggle('is-open');
        gatilho.setAttribute('aria-expanded', String(aberto));
        $$('[data-dropdown-panel]').forEach((outro) => {
          if (outro !== painel) outro.classList.remove('is-open');
        });
      });
    });

    document.addEventListener('click', () => {
      $$('[data-dropdown-panel]').forEach((p) => p.classList.remove('is-open'));
      $$('[data-dropdown-trigger]').forEach((g) => g.setAttribute('aria-expanded', 'false'));
    });

    document.addEventListener('keydown', (e) => {
      if (e.key !== 'Escape') return;
      $$('[data-dropdown-panel]').forEach((p) => p.classList.remove('is-open'));
      fecharDrawers();
    });
  }

  /* --------------------------------------------------------------- drawers */
  function fecharDrawers() {
    $$('.drawer.is-open').forEach((d) => d.classList.remove('is-open'));
    $$('.overlay.is-open').forEach((o) => o.classList.remove('is-open'));
    document.body.style.overflow = '';
  }

  function iniciarDrawers() {
    $$('[data-drawer-open]').forEach((botao) => {
      botao.addEventListener('click', (e) => {
        e.preventDefault();
        const drawer = $(botao.dataset.drawerOpen);
        if (!drawer) return;
        drawer.classList.add('is-open');
        $('.overlay')?.classList.add('is-open');
        document.body.style.overflow = 'hidden';
        $('button, a, input', drawer)?.focus();
      });
    });
    $$('[data-drawer-close]').forEach((b) => b.addEventListener('click', fecharDrawers));
    $('.overlay')?.addEventListener('click', fecharDrawers);
  }

  /* -------------------------------------------------------------- acordeão */
  function iniciarAcordeoes() {
    $$('[data-accordion]').forEach((item) => {
      const gatilho = $('[data-accordion-trigger]', item);
      gatilho?.addEventListener('click', () => item.classList.toggle('is-open'));
    });
  }

  /* ------------------------------------------------------------ carrosséis */
  function iniciarCarrosseis() {
    $$('[data-carousel]').forEach((raiz) => {
      const trilha = $('[data-carousel-track]', raiz);
      const anterior = $('[data-carousel-prev]', raiz);
      const proximo = $('[data-carousel-next]', raiz);
      if (!trilha) return;

      const passo = () => trilha.clientWidth * 0.8;
      const atualizarBotoes = () => {
        const fim = trilha.scrollWidth - trilha.clientWidth - 4;
        if (anterior) anterior.disabled = trilha.scrollLeft <= 4;
        if (proximo) proximo.disabled = trilha.scrollLeft >= fim;
      };

      anterior?.addEventListener('click', () => trilha.scrollBy({ left: -passo(), behavior: 'smooth' }));
      proximo?.addEventListener('click', () => trilha.scrollBy({ left: passo(), behavior: 'smooth' }));
      trilha.addEventListener('scroll', atualizarBotoes, { passive: true });
      window.addEventListener('resize', atualizarBotoes);
      atualizarBotoes();
    });
  }

  /* ------------------------------------------------- carrossel do hero */
  function iniciarHero() {
    const hero = $('[data-hero]');
    if (!hero) return;
    const slides = $$('[data-hero-slide]', hero);
    const pontos = $$('[data-hero-dot]', hero);
    if (slides.length < 2) return;

    let atual = 0;
    let timer = null;

    const mostrar = (indice) => {
      slides.forEach((s, i) => {
        s.hidden = i !== indice;
        if (i === indice && !reduzido) s.classList.add('anim-fade-in');
      });
      pontos.forEach((p, i) => p.classList.toggle('is-active', i === indice));
      atual = indice;
    };

    const proximo = () => mostrar((atual + 1) % slides.length);
    const iniciar = () => { if (!reduzido) timer = setInterval(proximo, 6500); };
    const parar = () => clearInterval(timer);

    pontos.forEach((p, i) =>
      p.addEventListener('click', () => { parar(); mostrar(i); iniciar(); })
    );
    hero.addEventListener('mouseenter', parar);
    hero.addEventListener('mouseleave', iniciar);

    mostrar(0);
    iniciar();
  }

  /* --------------------------------------------------------- contagem regressiva */
  function iniciarContadores() {
    const contadores = $$('[data-countdown]');
    if (!contadores.length) return;

    const doisDigitos = (n) => String(Math.max(0, n)).padStart(2, '0');

    const tick = () => {
      contadores.forEach((el) => {
        const alvo = new Date(el.dataset.countdown).getTime();
        const restante = alvo - Date.now();
        if (restante <= 0) {
          el.innerHTML = '<span class="countdown__unit"><span class="countdown__num">Encerrada</span></span>';
          return;
        }
        const dias = Math.floor(restante / 86400000);
        const horas = Math.floor((restante % 86400000) / 3600000);
        const minutos = Math.floor((restante % 3600000) / 60000);
        const segundos = Math.floor((restante % 60000) / 1000);
        const unidades = [
          [dias, 'dias'], [horas, 'horas'], [minutos, 'min'], [segundos, 'seg'],
        ];
        el.innerHTML = unidades
          .map(
            ([valor, rotulo]) =>
              `<span class="countdown__unit"><span class="countdown__num">${doisDigitos(valor)}</span>
               <span class="countdown__label">${rotulo}</span></span>`
          )
          .join('');
      });
    };
    tick();
    setInterval(tick, 1000);
  }

  /* --------------------------------------------- adicionar ao carrinho (AJAX) */
  function iniciarCarrinho() {
    document.addEventListener('submit', async (e) => {
      const form = e.target.closest('[data-cart-form]');
      if (!form) return;
      e.preventDefault();

      const botao = $('[type=submit]', form);
      const textoOriginal = botao ? botao.innerHTML : '';
      if (botao) {
        botao.classList.add('is-loading');
        botao.innerHTML = '<span class="spinner"></span> Adicionando...';
      }

      try {
        const resposta = await fetch(form.action, {
          method: 'POST',
          body: new FormData(form),
          headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': csrf() },
        });
        const dados = await resposta.json();
        toast(dados.mensagem, dados.ok ? 'success' : 'error');
        if (dados.ok) atualizarContadorCarrinho(dados.quantidade);
      } catch (erro) {
        form.submit(); // sem rede: cai no POST tradicional
        return;
      } finally {
        if (botao) {
          botao.classList.remove('is-loading');
          botao.innerHTML = textoOriginal;
        }
      }
    });
  }

  function atualizarContadorCarrinho(quantidade) {
    const contador = $('[data-cart-count]');
    if (!contador) return;
    contador.textContent = quantidade;
    contador.hidden = quantidade === 0;
    contador.classList.remove('anim-bump');
    void contador.offsetWidth; // força o reinício da animação
    contador.classList.add('anim-bump');
  }

  /* ------------------------------------------- seletores de opção (radio) */
  function iniciarOpcoes() {
    $$('[data-option-group]').forEach((grupo) => {
      const opcoes = $$('.option', grupo);
      const sincronizar = () =>
        opcoes.forEach((o) => {
          const entrada = $('input', o);
          o.classList.toggle('is-selected', entrada && entrada.checked);
        });
      opcoes.forEach((o) => {
        o.addEventListener('click', () => {
          const entrada = $('input', o);
          if (entrada && !entrada.checked) {
            entrada.checked = true;
            entrada.dispatchEvent(new Event('change', { bubbles: true }));
          }
          sincronizar();
        });
      });
      grupo.addEventListener('change', sincronizar);
      sincronizar();
    });
  }

  /* -------------------------------------------- galeria da página de produto */
  function iniciarGaleria() {
    const principal = $('[data-gallery-main]');
    if (!principal) return;
    $$('[data-gallery-thumb]').forEach((miniatura) => {
      miniatura.addEventListener('click', () => {
        const src = miniatura.dataset.galleryThumb;
        if (!src) return;
        principal.style.opacity = '0';
        setTimeout(() => {
          principal.src = src;
          principal.style.opacity = '1';
        }, 130);
        $$('[data-gallery-thumb]').forEach((m) => m.classList.remove('is-active'));
        miniatura.classList.add('is-active');
      });
    });
    principal.style.transition = 'opacity .13s ease';
  }

  /* ------------------------------------------------------- quantidade +/- */
  function iniciarQuantidade() {
    document.addEventListener('click', (e) => {
      const botao = e.target.closest('[data-qty]');
      if (!botao) return;
      const campo = $('input', botao.parentElement);
      if (!campo) return;
      const passo = botao.dataset.qty === 'mais' ? 1 : -1;
      const minimo = Number(campo.min || 1);
      const maximo = Number(campo.max || 999);
      campo.value = Math.min(maximo, Math.max(minimo, Number(campo.value || 1) + passo));
      campo.dispatchEvent(new Event('change', { bubbles: true }));
    });
  }

  /* ----------------------------------------------------- copiar para o clipboard */
  function iniciarCopiar() {
    document.addEventListener('click', async (e) => {
      const botao = e.target.closest('[data-copy]');
      if (!botao) return;
      const alvo = $(botao.dataset.copy);
      const texto = alvo ? (alvo.value || alvo.textContent).trim() : '';
      if (!texto) return;
      try {
        await navigator.clipboard.writeText(texto);
        toast('Copiado para a área de transferência!', 'success');
      } catch {
        toast('Não foi possível copiar. Selecione e copie manualmente.', 'error');
      }
    });
  }

  /* ----------------------------------------- polling do status do Pix */
  function iniciarPixPolling() {
    const caixa = $('[data-pix-status]');
    if (!caixa) return;
    const url = caixa.dataset.pixStatus;
    let tentativas = 0;

    const consultar = async () => {
      if (tentativas++ > 120) return; // ~10 min
      try {
        const resposta = await fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
        const dados = await resposta.json();
        const rotulo = $('[data-pix-label]');
        if (rotulo) rotulo.textContent = dados.rotulo;
        if (dados.pago) {
          toast('Pagamento confirmado!', 'success');
          setTimeout(() => (window.location.href = dados.url_pedido), 900);
          return;
        }
      } catch { /* rede instável: tenta de novo no próximo ciclo */ }
      setTimeout(consultar, 5000);
    };
    setTimeout(consultar, 5000);
  }

  /* ------------------------------------------------ máscaras de formulário */
  function mascarar(campo, formatador) {
    if (!campo) return;
    campo.addEventListener('input', () => {
      const posicaoFinal = campo.selectionStart === campo.value.length;
      campo.value = formatador(campo.value);
      if (posicaoFinal) campo.setSelectionRange(campo.value.length, campo.value.length);
    });
  }

  function iniciarMascaras() {
    const digitos = (v) => v.replace(/\D/g, '');

    $$('[data-mask="cep"]').forEach((c) =>
      mascarar(c, (v) => digitos(v).slice(0, 8).replace(/(\d{5})(\d)/, '$1-$2'))
    );
    $$('[data-mask="cpf"]').forEach((c) =>
      mascarar(c, (v) =>
        digitos(v).slice(0, 11)
          .replace(/(\d{3})(\d)/, '$1.$2')
          .replace(/(\d{3})\.(\d{3})(\d)/, '$1.$2.$3')
          .replace(/\.(\d{3})(\d{1,2})$/, '.$1-$2')
      )
    );
    $$('[data-mask="telefone"]').forEach((c) =>
      mascarar(c, (v) =>
        digitos(v).slice(0, 11)
          .replace(/(\d{2})(\d)/, '($1) $2')
          .replace(/(\d{5})(\d)/, '$1-$2')
      )
    );
    $$('[data-mask="cartao"]').forEach((c) =>
      mascarar(c, (v) => digitos(v).slice(0, 16).replace(/(\d{4})(?=\d)/g, '$1 '))
    );
    $$('[data-mask="validade"]').forEach((c) =>
      mascarar(c, (v) => digitos(v).slice(0, 4).replace(/(\d{2})(\d)/, '$1/$2'))
    );
    $$('[data-mask="cvv"]').forEach((c) => mascarar(c, (v) => digitos(v).slice(0, 4)));
  }

  /* ------------------------------------------ busca de CEP (ViaCEP) */
  function iniciarBuscaCep() {
    const campo = $('[data-cep-lookup]');
    if (!campo) return;
    campo.addEventListener('blur', async () => {
      const cep = campo.value.replace(/\D/g, '');
      if (cep.length !== 8) return;
      try {
        const resposta = await fetch(`https://viacep.com.br/ws/${cep}/json/`);
        const dados = await resposta.json();
        if (dados.erro) return;
        const preencher = (nome, valor) => {
          const alvo = $(`[name="${nome}"]`);
          if (alvo && !alvo.value) alvo.value = valor || '';
        };
        preencher('logradouro', dados.logradouro);
        preencher('bairro', dados.bairro);
        preencher('cidade', dados.localidade);
        preencher('uf', dados.uf);
        $('[name="numero"]')?.focus();
      } catch { /* offline: o usuário preenche à mão */ }
    });
  }

  /* --------------------------------------- barra de progresso do frete grátis */
  function iniciarBarraFrete() {
    $$('[data-freight-bar]').forEach((barra) => {
      const percentual = Math.min(100, Number(barra.dataset.freightBar || 0));
      requestAnimationFrame(() => { barra.style.width = `${percentual}%`; });
    });
  }

  /* ------------------------------------------ mensagens do Django viram toasts */
  function iniciarMensagens() {
    $$('[data-django-message]').forEach((el) => {
      toast(el.textContent.trim(), el.dataset.djangoMessage || 'info');
      el.remove();
    });
  }

  /* ------------------------------------------- convite de instalar o app
     O navegador dispara `beforeinstallprompt` só quando o site é instalável
     E ainda não foi instalado — então o convite nunca aparece para quem já
     tem o app. O atraso evita interromper quem acabou de chegar. */
  function iniciarConvitePwa() {
    const caixa = $('#pwa-convite');
    if (!caixa || !window.AGROCAMPO_PWA) return;

    const CHAVE = 'agrocampo_pwa_dispensado';
    const dispensadoEm = Number(localStorage.getItem(CHAVE) || 0);
    const SETE_DIAS = 7 * 24 * 60 * 60 * 1000;
    if (dispensadoEm && Date.now() - dispensadoEm < SETE_DIAS) return;

    // já rodando como app instalado: não faz sentido convidar
    if (window.matchMedia('(display-mode: standalone)').matches ||
        window.navigator.standalone) return;

    let evento = null;

    window.addEventListener('beforeinstallprompt', function (e) {
      e.preventDefault();
      evento = e;
      setTimeout(function () {
        if (!evento) return;
        caixa.hidden = false;
        caixa.classList.add('is-visivel');
      }, (window.AGROCAMPO_PWA.atrasoSegundos || 30) * 1000);
    });

    $('[data-pwa-instalar]', caixa).addEventListener('click', async function () {
      if (!evento) return;
      caixa.classList.remove('is-visivel');
      evento.prompt();
      const escolha = await evento.userChoice;
      evento = null;
      caixa.hidden = true;
      if (escolha.outcome === 'accepted') toast('App instalado. Bom proveito!', 'success');
      else localStorage.setItem(CHAVE, String(Date.now()));
    });

    $('[data-pwa-dispensar]', caixa).addEventListener('click', function () {
      caixa.classList.remove('is-visivel');
      setTimeout(function () { caixa.hidden = true; }, 300);
      localStorage.setItem(CHAVE, String(Date.now()));
    });

    window.addEventListener('appinstalled', function () {
      caixa.hidden = true;
      localStorage.removeItem(CHAVE);
    });
  }

  /* ------------------------------------------------------------------ boot */
  function iniciar() {
    iniciarReveal();
    iniciarHeader();
    iniciarDropdowns();
    iniciarDrawers();
    iniciarAcordeoes();
    iniciarCarrosseis();
    iniciarHero();
    iniciarContadores();
    iniciarCarrinho();
    iniciarOpcoes();
    iniciarGaleria();
    iniciarQuantidade();
    iniciarCopiar();
    iniciarPixPolling();
    iniciarMascaras();
    iniciarBuscaCep();
    iniciarBarraFrete();
    iniciarMensagens();
    iniciarConvitePwa();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', iniciar);
  } else {
    iniciar();
  }
})();
