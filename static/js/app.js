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
      // threshold 0: basta um pixel aparecer. Com uma fração (0.12) um bloco
      // mais alto que a janela — uma tabela com dezenas de produtos — nunca
      // alcançava a fração exigida e ficava invisível para sempre.
      { threshold: 0, rootMargin: '0px 0px -40px 0px' }
    );
    alvos.forEach((el) => {
      // bloco que já nasce ocupando a tela inteira não espera observador
      if (el.getBoundingClientRect().top < window.innerHeight) {
        el.classList.add('is-visible');
        return;
      }
      observador.observe(el);
    });

    // rede de segurança: nada neste site pode ficar invisível por causa de
    // animação. Se em 3 s algo ainda não apareceu, aparece.
    setTimeout(() => {
      alvos.forEach((el) => el.classList.add('is-visible'));
    }, 3000);
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
    // a home tem dois carrosséis: o do topo e o do fim da página. O mesmo
    // comportamento serve aos dois, cada um com o seu próprio relógio.
    $$('[data-hero]').forEach(montarHero);
  }

  function montarHero(hero) {
    const slides = $$('[data-hero-slide]', hero);
    const pontos = $$('[data-hero-dot]', hero);
    if (!slides.length) return;

    // um slide só não gira, mas o vídeo precisa tocar assim mesmo
    if (slides.length < 2) {
      $$('video', hero).forEach((video) => {
        const talvez = video.play();
        if (talvez && talvez.catch) talvez.catch(() => { video.controls = true; });
      });
      return;
    }

    let atual = 0;
    let timer = null;

    const mostrar = (indice) => {
      slides.forEach((s, i) => {
        const visivel = i === indice;
        s.hidden = !visivel;
        if (visivel && !reduzido) s.classList.add('anim-fade-in');

        /* O `autoplay` do HTML só vale no carregamento: slide de vídeo que
           nasce escondido nunca começava e o cliente via um retângulo preto.
           Ao entrar em cena o vídeo toca; ao sair, pausa — fora da tela é só
           bateria e dados do celular. */
        const video = s.querySelector('video');
        if (!video) return;
        if (visivel) {
          video.currentTime = 0;
          const talvez = video.play();
          // navegador que recusa o autoplay deixaria um retângulo preto sem
          // saída; com os controles à mostra o cliente dá o play
          if (talvez && talvez.catch) talvez.catch(() => { video.controls = true; });
        } else {
          video.pause();
        }
      });
      pontos.forEach((p, i) => p.classList.toggle('is-active', i === indice));
      atual = indice;
    };

    const proximo = () => { mostrar((atual + 1) % slides.length); iniciar(); };
    const iniciar = () => {
      clearTimeout(timer);
      const segundos = Number(slides[atual].dataset.tempo) || 6.5;
      if (!reduzido && !document.hidden && !hero.matches(':hover') && !hero.contains(document.activeElement)) {
        timer = setTimeout(proximo, Math.min(300, Math.max(1, segundos)) * 1000);
      }
    };
    const parar = () => clearTimeout(timer);

    pontos.forEach((p, i) =>
      p.addEventListener('click', () => { parar(); mostrar(i); iniciar(); })
    );
    // setas (estilo vitrine); no clássico não existem e nada acontece
    const anterior = () => mostrar((atual - 1 + slides.length) % slides.length);
    $$('[data-hero-prev]', hero).forEach(b => b.addEventListener('click', () => { parar(); anterior(); iniciar(); }));
    $$('[data-hero-next]', hero).forEach(b => b.addEventListener('click', () => { parar(); proximo(); iniciar(); }));
    /* Vídeo manda no próprio tempo: cortar no meio da fala é pior do que
       esperar, e deixar parado no último quadro depois do fim é pior ainda.
       O tempo do cadastro continua valendo como teto, lá no `iniciar()`. */
    $$('video', hero).forEach((video) => {
      video.loop = false;
      video.addEventListener('ended', () => {
        if (!video.closest('[data-hero-slide]').hidden) proximo();
      });
    });

    hero.addEventListener('mouseenter', parar);
    hero.addEventListener('mouseleave', iniciar);
    hero.addEventListener('focusin', parar);
    hero.addEventListener('focusout', () => setTimeout(iniciar, 0));
    document.addEventListener('visibilitychange', () => document.hidden ? parar() : iniciar());

    mostrar(0);
    iniciar();
  }

  /* ------------------------------------ banner de apresentação (topo) */
  function iniciarApresentacao() {
    const caixa = $('[data-apresentacao]');
    if (!caixa) return;

    const slides = $$('[data-apresentacao-slide]', caixa);
    const pontos = $$('[data-apresentacao-dot]', caixa);
    if (slides.length < 2) return;

    let atual = 0;
    let timer = null;

    const mostrar = (indice) => {
      slides.forEach((slide, i) => {
        const visivel = i === indice;
        slide.hidden = !visivel;

        // vídeo fora de cena não precisa continuar decodificando quadros:
        // no celular isso é bateria e dados do cliente
        const video = slide.querySelector('video');
        if (video) {
          if (visivel) {
            const talvez = video.play();
            if (talvez && talvez.catch) talvez.catch(() => {});
          } else {
            video.pause();
          }
        }
      });
      pontos.forEach((p, i) => p.classList.toggle('is-active', i === indice));
      atual = indice;
    };

    const proximo = () => { mostrar((atual + 1) % slides.length); iniciar(); };
    const iniciar = () => {
      clearTimeout(timer);
      const segundos = Number(slides[atual].dataset.tempo) || 6.5;
      if (!reduzido && !document.hidden && !caixa.matches(':hover') && !caixa.contains(document.activeElement)) {
        timer = setTimeout(proximo, Math.min(300, Math.max(1, segundos)) * 1000);
      }
    };
    const parar = () => clearTimeout(timer);

    pontos.forEach((p, i) =>
      p.addEventListener('click', () => { parar(); mostrar(i); iniciar(); })
    );
    caixa.addEventListener('mouseenter', parar);
    caixa.addEventListener('mouseleave', iniciar);
    caixa.addEventListener('focusin', parar);
    caixa.addEventListener('focusout', () => setTimeout(iniciar, 0));

    // com a aba escondida o intervalo continuaria trocando slides à toa
    document.addEventListener('visibilitychange', () =>
      document.hidden ? parar() : iniciar()
    );

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

      const botao = (e.submitter && e.submitter.form === form) ? e.submitter : $('[type=submit]', form);
      const textoOriginal = botao ? botao.innerHTML : '';
      const corpo = new FormData(form);
      if (e.submitter && e.submitter.name) corpo.append(e.submitter.name, e.submitter.value || '1');
      if (botao) {
        botao.classList.add('is-loading');
        botao.innerHTML = '<span class="spinner"></span> Adicionando...';
      }

      try {
        const resposta = await fetch(form.action, {
          method: 'POST',
          body: corpo,
          headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': csrf() },
        });
        const dados = await resposta.json();
        toast(dados.mensagem, dados.ok ? 'success' : 'error');
        if (dados.ok) atualizarContadorCarrinho(dados.quantidade);
        if (dados.ok && dados.redirecionar) { location.href = dados.redirecionar; return; }
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

  /* ------------------------------------------ cadastro em três passos */
  function iniciarCadastro() {
    const form = $('[data-cadastro]');
    if (!form) return;
    const telas = $$('[data-cadastro-tela]', form);
    const passos = $$('.passos__item');
    const btVoltar = $('[data-cadastro-voltar]', form);
    const btAvancar = $('[data-cadastro-avancar]', form);
    const btEnviar = $('[data-cadastro-enviar]', form);
    if (telas.length < 2) return;

    // o formulário nasce inteiro na tela: sem JS, o cadastro continua de pé.
    // Daqui para a frente é o JS que manda em quem aparece.
    let atual = 0;
    // se o servidor devolveu erro, começa no passo do primeiro campo errado
    const comErro = form.querySelector('.error-text');
    if (comErro) {
      const tela = comErro.closest('[data-cadastro-tela]');
      if (tela) atual = telas.indexOf(tela);
    }

    function mostrar(indice) {
      atual = Math.max(0, Math.min(indice, telas.length - 1));
      telas.forEach((t, i) => { t.hidden = i !== atual; });
      passos.forEach((p, i) => {
        p.classList.toggle('is-atual', i === atual);
        p.classList.toggle('is-feito', i < atual);
      });
      btVoltar.hidden = atual === 0;
      btAvancar.hidden = atual === telas.length - 1;
      btEnviar.hidden = atual !== telas.length - 1;
      const primeiro = telas[atual].querySelector('input:not([type=hidden])');
      if (primeiro) primeiro.focus();
    }

    function validaTela() {
      // deixa o próprio navegador cobrar os campos do passo visível
      const campos = $$('input, select', telas[atual]);
      for (const campo of campos) {
        if (!campo.checkValidity()) { campo.reportValidity(); return false; }
      }
      return true;
    }

    btAvancar.addEventListener('click', () => { if (validaTela()) mostrar(atual + 1); });
    btVoltar.addEventListener('click', () => mostrar(atual - 1));
    // Enter no meio do cadastro avança em vez de enviar pela metade
    form.addEventListener('keydown', (e) => {
      if (e.key !== 'Enter' || atual === telas.length - 1) return;
      if (e.target.tagName === 'TEXTAREA') return;
      e.preventDefault();
      if (validaTela()) mostrar(atual + 1);
    });

    mostrar(atual);
  }

  /* ------------------------- galeria passando no hover, nos cards da vitrine */
  function iniciarHoverGaleria() {
    // sem mouse (celular, tablet) não há hover: nada a fazer
    if (!window.matchMedia('(hover: hover)').matches) return;

    $$('[data-hover-galeria]').forEach((moldura) => {
      const foto = $('[data-hover-foto]', moldura);
      if (!foto) return;
      const fotos = (foto.dataset.fotos || '').split('|').filter(Boolean);
      if (fotos.length < 2) return;
      const pontos = $$('.product__pontos i', moldura);
      const capa = fotos[0];
      let i = 0, timer = null;

      // as outras fotos entram na memória do navegador antes do primeiro
      // hover: trocar e esperar o download pisca a imagem
      fotos.slice(1).forEach((src) => { const p = new Image(); p.src = src; });

      const mostrar = (indice) => {
        i = indice % fotos.length;
        foto.src = fotos[i];
        pontos.forEach((p, n) => p.classList.toggle('is-ativo', n === i));
      };

      moldura.addEventListener('mouseenter', () => {
        if (reduzido) return;
        timer = setInterval(() => mostrar(i + 1), 1100);
      });
      moldura.addEventListener('mouseleave', () => {
        clearInterval(timer);
        foto.src = capa;
        pontos.forEach((p, n) => p.classList.toggle('is-ativo', n === 0));
        i = 0;
      });
    });
  }

  /* ----------------------------------- player dos vídeos do Instagram */
  function iniciarStories() {
    const player = $('[data-stories-player]');
    if (!player) return;

    const gatilhos = $$('[data-story]');
    const fontes = $$('.reels__item').map((item) => ({
      video: item.dataset.video,
      link: item.dataset.link,
      legenda: item.dataset.legenda,
    }));
    if (!fontes.length) return;

    const video = $('[data-stories-video]', player);
    const barras = $('[data-stories-barras]', player);
    const legenda = $('[data-stories-legenda]', player);
    const link = $('[data-stories-link]', player);
    let atual = 0;

    // o player vive solto no <body>: dentro da seção, qualquer `transform`
    // de animação faria o `fixed` medir a caixa errada
    if (player.parentElement !== document.body) document.body.appendChild(player);

    function desenharBarras() {
      barras.innerHTML = fontes.map(() => '<i><span></span></i>').join('');
    }

    function andarBarra() {
      const partes = $$('span', barras);
      partes.forEach((p, i) => {
        p.style.transition = 'none';
        p.style.width = i < atual ? '100%' : '0';
      });
      const ativa = partes[atual];
      if (!ativa || !video.duration || !isFinite(video.duration)) return;
      ativa.style.transition = 'width ' + video.duration + 's linear';
      // o navegador precisa pintar o 0% antes de animar até 100%
      requestAnimationFrame(() => { ativa.style.width = '100%'; });
    }

    function mostrar(indice) {
      atual = (indice + fontes.length) % fontes.length;
      const dados = fontes[atual];
      video.src = dados.video;
      video.muted = false;
      video.play().catch(() => {
        // autoplay com som costuma ser recusado: tenta mudo, como o Instagram
        video.muted = true;
        video.play().catch(() => {});
      });
      legenda.textContent = dados.legenda || '';
      if (dados.link) { link.href = dados.link; link.hidden = false; }
      else { link.hidden = true; }
    }

    function abrir(indice) {
      desenharBarras();
      player.hidden = false;
      document.body.style.overflow = 'hidden';
      mostrar(indice);
    }

    function fechar() {
      player.hidden = true;
      video.pause();
      video.removeAttribute('src');
      document.body.style.overflow = '';
    }

    gatilhos.forEach((g) => {
      g.addEventListener('click', () => abrir(Number(g.dataset.story) || 0));
    });
    video.addEventListener('loadedmetadata', andarBarra);
    video.addEventListener('ended', () => {
      // no último, fecha: seguir girando sem fim prende quem já viu tudo
      if (atual === fontes.length - 1) fechar();
      else mostrar(atual + 1);
    });

    $('[data-stories-fechar]', player).addEventListener('click', fechar);
    $('[data-stories-proximo]', player).addEventListener('click', () => mostrar(atual + 1));
    $('[data-stories-anterior]', player).addEventListener('click', () => mostrar(atual - 1));
    document.addEventListener('keydown', (e) => {
      if (player.hidden) return;
      if (e.key === 'Escape') fechar();
      if (e.key === 'ArrowRight') mostrar(atual + 1);
      if (e.key === 'ArrowLeft') mostrar(atual - 1);
    });

    // no celular: toque na metade direita avança, na esquerda volta
    video.addEventListener('click', (e) => {
      const r = video.getBoundingClientRect();
      mostrar(atual + (e.clientX - r.left > r.width / 2 ? 1 : -1));
    });
  }

  /* -------------------------------------------- galeria da página de produto */
  function iniciarGaleria() {
    const principal = $('[data-gallery-main]');
    if (!principal) return;

    const moldura = $('[data-ampliar]');
    const lente = $('[data-lente]');
    const painel = $('[data-zoom]');
    const lupa = $('[data-lupa]');
    const lupaImg = $('[data-lupa-img]');
    const passos = $('[data-lupa-passos]');
    const miniaturas = $$('[data-gallery-thumb]');
    const temMouse = window.matchMedia('(hover: hover)').matches;

    // as fotos na ordem em que estão na galeria: serve ao arrasto da tela cheia
    const fotos = miniaturas.length
      ? miniaturas.map((m) => m.dataset.galleryThumb)
      : [principal.currentSrc || principal.src];
    let atual = 0;

    /* ------------------------------------------------ troca de foto */
    function trocar(indice, vindoDaMiniatura) {
      atual = (indice + fotos.length) % fotos.length;
      principal.style.opacity = '0';
      setTimeout(() => {
        principal.src = fotos[atual];
        principal.style.opacity = '1';
      }, 120);
      miniaturas.forEach((m, i) => {
        m.classList.toggle('is-active', i === atual);
        m.setAttribute('aria-selected', i === atual ? 'true' : 'false');
      });
      if (!lupa.hidden) mostrarNaLupa();
      if (!vindoDaMiniatura && miniaturas[atual]) {
        miniaturas[atual].scrollIntoView({ block: 'nearest', inline: 'nearest' });
      }
    }
    principal.style.transition = 'opacity .12s ease';

    miniaturas.forEach((miniatura, i) => {
      miniatura.addEventListener('click', () => trocar(i, true));
      // passar o mouse já troca: é como o cliente espera de marketplace
      if (temMouse) miniatura.addEventListener('mouseenter', () => trocar(i, true));
    });

    /* ------------------------------- lente + painel (só com mouse)
       A foto fica parada no quadro. O que se move é a lente; o painel ao
       lado mostra o mesmo pedaço ampliado, usando a imagem em tamanho
       original — esticar a miniatura daria uma mancha borrada. */
    const AMPLIACAO = 2.4;

    function posicionarZoom(e) {
      const r = moldura.getBoundingClientRect();
      const larguraLente = r.width / AMPLIACAO;
      const alturaLente = r.height / AMPLIACAO;

      let x = e.clientX - r.left - larguraLente / 2;
      let y = e.clientY - r.top - alturaLente / 2;
      x = Math.max(0, Math.min(x, r.width - larguraLente));
      y = Math.max(0, Math.min(y, r.height - alturaLente));

      lente.style.width = larguraLente + 'px';
      lente.style.height = alturaLente + 'px';
      lente.style.left = x + 'px';
      lente.style.top = y + 'px';
      lente.hidden = false;

      painel.hidden = false;
      painel.style.backgroundImage = 'url("' + (principal.currentSrc || principal.src) + '")';
      painel.style.backgroundSize =
        (r.width * AMPLIACAO) + 'px ' + (r.height * AMPLIACAO) + 'px';
      painel.style.backgroundPosition = (-x * AMPLIACAO) + 'px ' + (-y * AMPLIACAO) + 'px';
    }

    function esconderZoom() {
      if (lente) lente.hidden = true;
      if (painel) { painel.hidden = true; painel.style.backgroundImage = ''; }
    }

    if (temMouse && lente && painel && !reduzido) {
      moldura.addEventListener('mousemove', posicionarZoom);
      moldura.addEventListener('mouseleave', esconderZoom);
      // trocar de foto com o painel aberto não pode deixar a anterior nele
      moldura.addEventListener('mouseenter', esconderZoom);
    }

    /* ------------------------------------------- tela cheia (toque) */
    if (!lupa || !lupaImg) return;

    /* O visor é `position: fixed`, mas a galeria entra na tela com uma
       animação de `transform` — e elemento transformado vira o novo
       referencial do `fixed`. No celular o visor ficava preso dentro da
       moldura, torto e por cima do produto. Mudando-o para o <body> ele
       volta a medir a tela inteira. */
    if (lupa.parentElement !== document.body) document.body.appendChild(lupa);

    function mostrarNaLupa() {
      lupaImg.src = fotos[atual];
      if (!passos) return;
      passos.hidden = fotos.length < 2;
      passos.innerHTML = fotos
        .map((_, i) => '<i class="' + (i === atual ? 'is-ativo' : '') + '"></i>')
        .join('');
    }

    const abrir = () => {
      esconderZoom();
      mostrarNaLupa();
      lupa.hidden = false;
      document.body.style.overflow = 'hidden';
    };
    const fechar = () => {
      lupa.hidden = true;
      document.body.style.overflow = '';
    };

    moldura.addEventListener('click', abrir);
    moldura.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); abrir(); }
    });

    // clicar no fundo fecha; na foto, não — senão a pinça fecharia sozinha
    lupa.addEventListener('click', (e) => {
      if (e.target === lupaImg) return;
      fechar();
    });
    document.addEventListener('keydown', (e) => {
      if (lupa.hidden) return;
      if (e.key === 'Escape') fechar();
      if (e.key === 'ArrowRight') trocar(atual + 1);
      if (e.key === 'ArrowLeft') trocar(atual - 1);
    });

    /* Arrasto para trocar de foto. Só conta o gesto de um dedo: com dois, o
       cliente está dando pinça para ampliar, e trocar a foto no meio disso
       seria o contrário do que ele pediu. */
    let origemX = 0;
    let dedos = 0;
    lupa.addEventListener('touchstart', (e) => {
      dedos = e.touches.length;
      origemX = e.touches[0].clientX;
    }, { passive: true });
    lupa.addEventListener('touchend', (e) => {
      if (dedos !== 1 || fotos.length < 2) return;
      const fim = (e.changedTouches[0] || {}).clientX || origemX;
      const distancia = fim - origemX;
      if (Math.abs(distancia) < 50) return;
      trocar(atual + (distancia < 0 ? 1 : -1));
      mostrarNaLupa();
    }, { passive: true });
  }

  /* --------------------------------- tamanhos (variações) do produto */
  function iniciarTamanhos() {
    const grupo = $('[data-tamanhos]');
    if (!grupo) return;

    const precoAtual = $('[data-preco-atual]');
    const precoAntigo = $('[data-preco-antigo]');
    const rotuloEstoque = $('[data-estoque-rotulo]');
    const campoQtd = $('[data-qty-input]');
    const imagem = $('[data-gallery-main]');

    function aplicar(opcao) {
      const d = opcao.dataset;
      if (precoAtual) precoAtual.textContent = d.preco || precoAtual.textContent;

      if (precoAntigo) {
        precoAntigo.textContent = d.precoCheio || '';
        precoAntigo.hidden = !d.precoCheio;
      }

      if (rotuloEstoque && d.rotuloEstoque) {
        rotuloEstoque.textContent = d.rotuloEstoque;
        rotuloEstoque.style.color = Number(d.estoque) > 0 ? 'var(--green)' : 'var(--red)';
      }

      if (campoQtd && d.estoque) {
        campoQtd.max = d.estoque;
        // o carrinho recusaria mais do que existe deste tamanho
        if (Number(campoQtd.value) > Number(d.estoque)) campoQtd.value = d.estoque || 1;
      }

      // o bloco de assinatura precisa seguir junto: prometer o desconto do
      // 15kg enquanto o cliente escolheu o 2kg é anunciar preço errado
      const unico = $('[data-preco-unico]');
      if (unico && d.preco) unico.textContent = d.preco;
      $$('[data-preco-assinatura]').forEach((el) => {
        if (d.assinatura) el.textContent = d.assinatura;
      });
      $$('[data-economia-assinatura]').forEach((el) => {
        if (d.economia) el.textContent = d.economia;
      });

      if (imagem && d.imagem) {
        imagem.style.opacity = '0';
        setTimeout(() => { imagem.src = d.imagem; imagem.style.opacity = '1'; }, 130);
      }
    }

    grupo.addEventListener('change', (e) => {
      const opcao = e.target.closest('input[name=variacao]');
      if (opcao && opcao.checked) aplicar(opcao);
    });

    const inicial = $('input[name=variacao]:checked', grupo);
    if (inicial) aplicar(inicial);
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
    iniciarApresentacao();
    iniciarGaleria();
    iniciarStories();
    iniciarHoverGaleria();
    iniciarCadastro();
    iniciarTamanhos();
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

/* ------------------------------------------- calculadora de frete (produto) */
(function () {
  const caixa = document.querySelector('[data-frete-calc]');
  if (!caixa) return;
  const cidade = caixa.querySelector('[data-frete-cidade]');
  const local = caixa.querySelector('[data-frete-localidade]');
  const botao = caixa.querySelector('[data-frete-calcular]');
  const saida = caixa.querySelector('[data-frete-resultado]');
  const opcoesLocal = Array.from(local.options);

  function filtrarLocalidades() {
    const id = cidade.value;
    let tem = false;
    opcoesLocal.forEach(o => {
      if (!o.dataset.cidade) return;
      const mostra = o.dataset.cidade === id;
      o.hidden = !mostra;
      if (mostra) tem = true;
    });
    local.value = '';
    local.hidden = !tem;
  }
  cidade.addEventListener('change', filtrarLocalidades);
  filtrarLocalidades();

  async function calcular() {
    if (!cidade.value) { saida.hidden = false; saida.textContent = 'Escolha a cidade.'; return; }
    const qtd = document.querySelector('[data-qty-input]');
    const subtotal = (parseFloat(caixa.dataset.preco) || 0) * (qtd ? parseInt(qtd.value, 10) || 1 : 1);
    const p = new URLSearchParams({ cidade: cidade.value, localidade: local.value, subtotal: subtotal.toFixed(2) });
    saida.hidden = false; saida.textContent = 'Calculando…';
    try {
      const r = await fetch(caixa.dataset.url + '?' + p.toString(), { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
      const d = await r.json();
      const valor = d.gratis ? '<strong style="color:var(--green)">Frete grátis</strong>' : '<strong>R$ ' + d.valor + '</strong>';
      const prazo = d.prazo_extenso ? ' · entrega prevista ' + d.prazo_extenso : '';
      const avisos = (d.avisos || []).map(a => '<div class="xs muted">' + a + '</div>').join('');
      saida.innerHTML = valor + prazo + avisos;
    } catch (e) {
      saida.textContent = 'Não consegui calcular agora.';
    }
  }
  botao.addEventListener('click', calcular);
})();

/* ------------------------------------------------- busca com sugestões */
(function () {
  const forms = document.querySelectorAll('form[data-sugestoes]');
  if (!forms.length) return;
  const esc = (t) => String(t || '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const icone = (n) => '<svg width="15" height="15" aria-hidden="true"><use href="#i-' + n + '"></use></svg>';

  forms.forEach((form) => {
    const input = form.querySelector('input[name="q"]');
    const painel = form.querySelector('[data-sugestoes-painel]');
    if (!input || !painel) return;
    let timer = null, ultimo = '', ativo = -1, controlador = null;

    function render(d) {
      if (!d.grupos || !d.grupos.length) {
        if (d.termo && d.termo.length >= 2) {
          painel.innerHTML = '<div class="sugestoes__vazio">Nada para “' + esc(d.termo) + '”. Tente outra palavra.</div>';
          abrir();
        } else fechar();
        return;
      }
      let html = '';
      d.grupos.forEach((g) => {
        html += '<div class="sugestoes__grupo">' + esc(g.titulo) + '</div>';
        g.itens.forEach((it) => {
          if (g.produtos) {
            html += '<a class="sugestoes__item sugestoes__item--produto" href="' + esc(it.url) + '" role="option">'
              + (it.foto ? '<img src="' + esc(it.foto) + '" alt="" loading="lazy">' : '<span class="sugestoes__semfoto"></span>')
              + '<span class="sugestoes__texto"><strong>' + esc(it.rotulo) + '</strong>'
              + (it.extra ? '<span class="sugestoes__extra">' + esc(it.extra) + '</span>' : '')
              + '<span class="sugestoes__preco">' + (it.a_partir ? 'a partir de ' : '') + esc(it.preco) + '</span></span></a>';
          } else {
            html += '<a class="sugestoes__item" href="' + esc(it.url) + '" role="option">' + icone(it.icone || 'busca')
              + '<span class="sugestoes__texto"><strong>' + esc(it.rotulo) + '</strong></span>'
              + (it.extra ? '<span class="sugestoes__extra">' + esc(it.extra) + '</span>' : '') + '</a>';
          }
        });
      });
      if (d.ver_todos) html += '<a class="sugestoes__todos" href="' + esc(d.ver_todos) + '">Ver todos os resultados para “' + esc(d.termo) + '” →</a>';
      painel.innerHTML = html;
      ativo = -1;
      abrir();
    }
    function abrir() { painel.hidden = false; input.setAttribute('aria-expanded', 'true'); }
    function fechar() { painel.hidden = true; input.setAttribute('aria-expanded', 'false'); ativo = -1; }

    async function buscar() {
      const termo = input.value.trim();
      if (termo === ultimo && !painel.hidden) return;
      ultimo = termo;
      if (controlador) controlador.abort();
      controlador = new AbortController();
      try {
        const r = await fetch(form.dataset.sugestoes + '?q=' + encodeURIComponent(termo), {
          headers: { 'X-Requested-With': 'XMLHttpRequest' }, signal: controlador.signal,
        });
        render(await r.json());
      } catch (e) { /* abortado ou sem rede: a busca normal continua funcionando */ }
    }

    input.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(buscar, 180); });
    input.addEventListener('focus', () => { clearTimeout(timer); timer = setTimeout(buscar, 120); });
    input.addEventListener('keydown', (e) => {
      const itens = painel.querySelectorAll('a');
      if (painel.hidden || !itens.length) { if (e.key === 'Escape') fechar(); return; }
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        ativo = e.key === 'ArrowDown' ? (ativo + 1) % itens.length : (ativo - 1 + itens.length) % itens.length;
        itens.forEach((a, i) => a.classList.toggle('is-ativo', i === ativo));
        itens[ativo].scrollIntoView({ block: 'nearest' });
      } else if (e.key === 'Enter' && ativo >= 0) {
        e.preventDefault(); location.href = itens[ativo].href;
      } else if (e.key === 'Escape') fechar();
    });
    document.addEventListener('click', (e) => { if (!form.contains(e.target)) fechar(); });
  });
})();
