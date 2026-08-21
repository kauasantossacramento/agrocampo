/* ============================================================================
   AgroCampo — painel do lojista.
   Carregado só nas telas do painel: a loja não precisa do wizard.
   Depende de `agroToast` exposto pelo app.js.
   ========================================================================== */
(function () {
  'use strict';

  const $ = (sel, ctx = document) => ctx.querySelector(sel);
  const $$ = (sel, ctx = document) => Array.from(ctx.querySelectorAll(sel));
  const toast = (m, t) => (window.agroToast ? window.agroToast(m, t) : null);

  function csrf() {
    const campo = $('[name=csrfmiddlewaretoken]');
    if (campo) return campo.value;
    const match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? match[1] : '';
  }

  /* ═══════════════════════════════════════════════ modal genérico */
  function abrirModal(titulo, html) {
    let modal = $('#modal-painel');
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'modal-painel';
      modal.className = 'modal';
      modal.setAttribute('role', 'dialog');
      modal.setAttribute('aria-modal', 'true');
      modal.innerHTML =
        '<div class="modal__caixa">' +
        '  <header class="modal__topo">' +
        '    <h2 data-modal-titulo></h2>' +
        '    <button type="button" class="icon-btn" data-modal-fechar aria-label="Fechar">' +
        '      <svg width="20" height="20"><use href="#i-x"></use></svg>' +
        '    </button>' +
        '  </header>' +
        '  <div class="modal__corpo" data-modal-corpo></div>' +
        '</div>';
      document.body.appendChild(modal);

      modal.addEventListener('click', function (e) {
        if (e.target === modal || e.target.closest('[data-modal-fechar]')) fecharModal();
      });
      document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && modal.classList.contains('is-open')) fecharModal();
      });
    }
    $('[data-modal-titulo]', modal).textContent = titulo;
    $('[data-modal-corpo]', modal).innerHTML = html;
    modal.classList.add('is-open');
    document.body.style.overflow = 'hidden';
    return modal;
  }

  function fecharModal() {
    const modal = $('#modal-painel');
    if (!modal) return;
    modal.classList.remove('is-open');
    document.body.style.overflow = '';
  }

  /* ═══════════════════════════════════════ wizard de produto */
  function iniciarWizardProduto() {
    document.addEventListener('click', async function (e) {
      const gatilho = e.target.closest('[data-produto-modal]');
      if (!gatilho) return;
      e.preventDefault();

      abrirModal(
        gatilho.dataset.produtoTitulo || 'Novo produto',
        '<p class="small muted">Carregando…</p>'
      );

      try {
        const resposta = await fetch(gatilho.dataset.produtoModal, {
          headers: { 'X-Requested-With': 'XMLHttpRequest' },
        });
        $('[data-modal-corpo]').innerHTML = await resposta.text();
        prepararWizard();
      } catch (erro) {
        $('[data-modal-corpo]').innerHTML =
          '<div class="alert alert--error">Não consegui carregar o formulário. Tente de novo.</div>';
      }
    });
  }

  function prepararWizard() {
    const wizard = $('[data-wizard]');
    if (!wizard) return;

    const telas = $$('[data-tela]', wizard);
    const passos = $$('.wizard__passo', wizard);
    const btVoltar = $('[data-wizard-voltar]', wizard);
    const btAvancar = $('[data-wizard-avancar]', wizard);
    const btSalvar = $('[data-wizard-salvar]', wizard);

    const novasFotos = [];   // File[] ainda não enviados
    const removidas = [];    // ids de ProdutoImagem marcados para apagar
    let atual = 0;

    function mostrar(indice) {
      atual = Math.max(0, Math.min(indice, telas.length - 1));
      telas.forEach(function (t, i) { t.hidden = i !== atual; });
      passos.forEach(function (p, i) {
        p.classList.toggle('is-atual', i === atual);
        p.classList.toggle('is-feito', i < atual);
      });
      btVoltar.hidden = atual === 0;
      btAvancar.hidden = atual === telas.length - 1;
      btSalvar.hidden = atual !== telas.length - 1;
      const corpo = $('.modal__corpo');
      if (corpo) corpo.scrollTo({ top: 0, behavior: 'smooth' });
    }

    // valida apenas os obrigatórios da etapa visível
    function telaValida() {
      const nomes = ['nome', 'categoria', 'preco', 'estoque'];
      const campos = $$('input, select, textarea', telas[atual]).filter(function (c) {
        return nomes.indexOf(c.name) > -1 || c.required;
      });
      for (let i = 0; i < campos.length; i++) {
        if (!campos[i].value) {
          campos[i].focus();
          campos[i].classList.add('anim-bump');
          setTimeout(function () { campos[i].classList.remove('anim-bump'); }, 400);
          toast('Preencha os campos obrigatórios desta etapa.', 'error');
          return false;
        }
      }
      return true;
    }

    btAvancar.addEventListener('click', function () {
      if (telaValida()) mostrar(atual + 1);
    });
    btVoltar.addEventListener('click', function () { mostrar(atual - 1); });
    $('[data-wizard-cancelar]', wizard).addEventListener('click', fecharModal);

    /* -------------------------------------------------------- fotos */
    const grade = $('[data-foto-previa]', wizard);
    const vazio = $('[data-foto-vazio]', wizard);

    function atualizarVazio() {
      if (vazio) vazio.hidden = grade.children.length > 0;
    }

    $$('[data-foto-input]', wizard).forEach(function (input) {
      input.addEventListener('change', function () {
        Array.prototype.forEach.call(input.files, function (arquivo) {
          novasFotos.push(arquivo);

          // prévia local: o lojista confere a foto antes de qualquer upload
          const url = URL.createObjectURL(arquivo);
          const figura = document.createElement('figure');
          figura.className = 'foto-item';

          const img = document.createElement('img');
          img.src = url;
          img.alt = '';

          const botao = document.createElement('button');
          botao.type = 'button';
          botao.className = 'foto-item__remover';
          botao.setAttribute('aria-label', 'Remover foto');
          botao.innerHTML = '<svg width="14" height="14"><use href="#i-x"></use></svg>';
          botao.addEventListener('click', function () {
            const posicao = novasFotos.indexOf(arquivo);
            if (posicao > -1) novasFotos.splice(posicao, 1);
            URL.revokeObjectURL(url);
            figura.remove();
            atualizarVazio();
          });

          figura.appendChild(img);
          figura.appendChild(botao);
          grade.appendChild(figura);
        });
        input.value = '';   // permite reescolher o mesmo arquivo
        atualizarVazio();
      });
    });

    $$('[data-remover-foto]', wizard).forEach(function (botao) {
      botao.addEventListener('click', function () {
        const id = botao.dataset.removerFoto;
        const item = botao.closest('.foto-item');
        const posicao = removidas.indexOf(id);
        if (posicao > -1) {
          removidas.splice(posicao, 1);
          item.classList.remove('is-removida');
        } else {
          removidas.push(id);
          item.classList.add('is-removida');
        }
      });
    });

    /* ------------------------------------------------------- salvar */
    btSalvar.addEventListener('click', async function () {
      if (!telaValida()) return;

      const dados = new FormData();
      $$('input, select, textarea', wizard).forEach(function (campo) {
        if (!campo.name || campo.type === 'file') return;
        if ((campo.type === 'checkbox' || campo.type === 'radio') && !campo.checked) return;
        dados.append(campo.name, campo.value);
      });
      novasFotos.forEach(function (f) { dados.append('fotos', f); });
      removidas.forEach(function (id) { dados.append('remover_imagem', id); });

      const textoOriginal = btSalvar.innerHTML;
      btSalvar.classList.add('is-loading');
      btSalvar.innerHTML = '<span class="spinner"></span> Salvando…';

      try {
        const resposta = await fetch(wizard.dataset.acao, {
          method: 'POST',
          body: dados,
          headers: { 'X-CSRFToken': csrf(), 'X-Requested-With': 'XMLHttpRequest' },
        });
        const json = await resposta.json();

        if (json.ok) {
          toast(json.criado ? 'Produto cadastrado!' : 'Produto atualizado!', 'success');
          fecharModal();
          setTimeout(function () { window.location.reload(); }, 700);
          return;
        }

        // devolve o formulário com os erros, sem perder o que já foi digitado
        $('[data-modal-corpo]').innerHTML = json.html;
        prepararWizard();
        toast('Confira os campos destacados.', 'error');
      } catch (erro) {
        toast('Não consegui salvar. Verifique a conexão.', 'error');
      } finally {
        btSalvar.classList.remove('is-loading');
        btSalvar.innerHTML = textoOriginal;
      }
    });

    mostrar(0);
    atualizarVazio();
  }

  /* ═══════════════════════════════════ abas das configurações */
  function iniciarAbas() {
    const abas = $$('[data-aba]');
    if (!abas.length) return;

    function trocar(chave, comHistorico) {
      abas.forEach(function (a) {
        a.classList.toggle('is-atual', a.dataset.aba === chave);
      });
      $$('[data-painel-aba]').forEach(function (p) {
        p.hidden = p.dataset.painelAba !== chave;
      });
      if (comHistorico !== false) {
        const url = new URL(window.location);
        url.searchParams.set('aba', chave);
        history.replaceState({}, '', url);
      }
    }

    abas.forEach(function (a) {
      a.addEventListener('click', function (e) {
        e.preventDefault();
        trocar(a.dataset.aba);
      });
    });

    const inicial = new URL(window.location).searchParams.get('aba');
    const existe = inicial && $('[data-aba="' + inicial + '"]');
    trocar(existe ? inicial : abas[0].dataset.aba, false);
  }

  /* ═════════════════════ pré-visualização ao vivo da aparência */
  function iniciarPreviaAparencia() {
    const previa = $('[data-previa]');
    if (!previa) return;

    [
      ['[name=nome_loja]', '[data-previa-nome]'],
      ['[name=chamada]', '[data-previa-chamada]'],
      ['[name=descricao]', '[data-previa-descricao]'],
      ['[name=topbar_mensagem]', '[data-previa-topbar]'],
      ['[name=topbar_icone]', '[data-previa-topbar-icone]'],
    ].forEach(function (par) {
      const campo = $(par[0]);
      const alvo = $(par[1], previa);
      if (!campo || !alvo) return;
      const aplicar = function () { alvo.textContent = campo.value || ''; };
      campo.addEventListener('input', aplicar);
      aplicar();
    });

    // troca a imagem na hora, sem precisar salvar antes
    [
      ['[name=logo]', '[data-previa-logo]'],
      ['[name=imagem_capa]', '[data-previa-figura]'],
    ].forEach(function (par) {
      const campo = $(par[0]);
      const alvo = $(par[1], previa);
      if (!campo || !alvo) return;
      campo.addEventListener('change', function () {
        const arquivo = campo.files && campo.files[0];
        if (arquivo) alvo.src = URL.createObjectURL(arquivo);
      });
    });
  }

  function iniciar() {
    iniciarWizardProduto();
    iniciarAbas();
    iniciarPreviaAparencia();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', iniciar);
  } else {
    iniciar();
  }
})();
