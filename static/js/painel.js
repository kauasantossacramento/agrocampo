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

  /* ══════════════════ campos de imagem das configurações */
  function iniciarCamposImagem() {
    document.addEventListener('change', function (e) {
      const campo = e.target;
      if (campo.type !== 'file' || !campo.closest('.campo-imagem')) return;

      // confirma para o lojista que o arquivo entrou: antes o botão dizia
      // "Enviar" mesmo depois de escolher, e parecia que nada aconteceu
      const rotulo = campo.closest('label').querySelector('[data-nome-arquivo]');
      if (rotulo && campo.files.length) rotulo.textContent = campo.files[0].name;

      const previa = campo.closest('.campo-imagem').querySelector('.campo-imagem__previa');
      if (previa && campo.files.length) {
        const url = URL.createObjectURL(campo.files[0]);
        previa.innerHTML = '';
        const img = document.createElement('img');
        img.src = url;
        img.alt = '';
        img.onload = function () { URL.revokeObjectURL(url); };
        previa.appendChild(img);
      }
    });
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
        if (!resposta.ok) throw new Error('HTTP ' + resposta.status);
        $('[data-modal-corpo]').innerHTML = await resposta.text();
      } catch (erro) {
        $('[data-modal-corpo]').innerHTML =
          '<div class="alert alert--error">Não consegui carregar o formulário. Tente de novo.</div>';
        return;
      }

      // fora do try de propósito: com `prepararWizard` lá dentro, qualquer
      // erro de JS trocava o formulário já carregado pela mensagem de falha —
      // o lojista via "não consegui carregar" com o servidor respondendo 200
      prepararWizard();
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
      if (btVoltar) btVoltar.hidden = atual === 0;
      if (btAvancar) btAvancar.hidden = atual === telas.length - 1;
      if (btSalvar) btSalvar.hidden = atual !== telas.length - 1;
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

    if (btAvancar) {
      btAvancar.addEventListener('click', function () {
        if (telaValida()) mostrar(atual + 1);
      });
    }
    if (btVoltar) {
      btVoltar.addEventListener('click', function () { mostrar(atual - 1); });
    }
    const btCancelar = $('[data-wizard-cancelar]', wizard);
    if (btCancelar) btCancelar.addEventListener('click', fecharModal);

    /* -------------------------------------------------------- fotos */
    const grade = $('[data-foto-previa]', wizard);
    const vazio = $('[data-foto-vazio]', wizard);

    function atualizarVazio() {
      if (vazio && grade) vazio.hidden = grade.children.length > 0;
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
          if (grade) grade.appendChild(figura);
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

    /* --------------------------------------------- tamanhos (variações) */
    const caixaVariacoes = $('[data-variacoes]', wizard);
    const modeloVariacao = $('[data-variacao-modelo]', wizard);
    const vazioVariacao = $('[data-variacao-vazio]', wizard);
    // o índice nunca é reaproveitado: reindexar linhas existentes trocaria
    // o arquivo de foto de uma pela da outra. `caixaVariacoes` é nulo em todo
    // modal que não seja o de produto — banners, cidades, cupons.
    let proximoIndice = caixaVariacoes
      ? $$('[data-variacao]', caixaVariacoes).length
      : 0;

    function atualizarVazioVariacao() {
      if (vazioVariacao) {
        vazioVariacao.hidden = caixaVariacoes.children.length > 0;
      }
    }

    function ligarRemocao(linha) {
      const botao = $('[data-variacao-remover]', linha);
      if (botao) {
        botao.addEventListener('click', function () {
          linha.remove();
          atualizarVazioVariacao();
        });
      }
      const foto = $('[data-variacao-foto]', linha);
      if (foto) {
        foto.addEventListener('change', function () {
          const rotulo = foto.closest('label').querySelector('span');
          if (foto.files.length && rotulo) rotulo.textContent = foto.files[0].name;
        });
      }
    }

    if (caixaVariacoes) {
      $$('[data-variacao]', caixaVariacoes).forEach(ligarRemocao);

      const btAdicionar = $('[data-variacao-add]', wizard);
      if (btAdicionar && modeloVariacao) {
        btAdicionar.addEventListener('click', function () {
          const i = proximoIndice++;
          const html = modeloVariacao.innerHTML.split('__i__').join(String(i));
          const temporario = document.createElement('div');
          temporario.innerHTML = html.trim();
          const linha = temporario.firstElementChild;
          caixaVariacoes.appendChild(linha);
          ligarRemocao(linha);
          atualizarVazioVariacao();
          const primeiro = $('input', linha);
          if (primeiro) primeiro.focus();
        });
      }
    }

    /* ------------------------------------------------------- salvar */
    if (!btSalvar) return;

    btSalvar.addEventListener('click', async function () {
      if (!telaValida()) return;

      // quando o servidor devolve o formulário com erros, ele precisa ser
      // religado — mas fora do try, senão um erro de JS apagaria a tela
      let recarregado = false;

      // barra antes de gastar o 4G do lojista com um envio que vai falhar
      const limites = { video: 60, imagem: 10, logo: 10, favicon: 10 };
      const grande = $$('input[type=file]', wizard).find(function (campo) {
        const limite = limites[campo.name] || 10;
        return campo.files.length && campo.files[0].size > limite * 1024 * 1024;
      });
      if (grande) {
        const limite = limites[grande.name] || 10;
        const mb = (grande.files[0].size / 1024 / 1024).toFixed(1);
        toast(
          'O arquivo tem ' + mb + ' MB e o limite é ' + limite +
          ' MB. Comprima e tente de novo.',
          'error'
        );
        return;
      }

      const dados = new FormData();
      // o conteúdo do <template> dos tamanhos vive num fragmento à parte,
      // então nem aparece aqui — só as linhas realmente adicionadas entram
      $$('input, select, textarea', wizard).forEach(function (campo) {
        if (!campo.name) return;

        if (campo.type === 'file') {
          // as fotos do produto já foram para `novasFotos`; mandar de novo
          // criaria a mesma imagem duas vezes
          if (campo.hasAttribute('data-foto-input')) return;
          // qualquer outro arquivo — logo, vídeo do banner, foto do tamanho —
          // segue pelo próprio nome. Antes todo input de arquivo era
          // descartado aqui, e o lojista não conseguia subir imagem de banner.
          Array.prototype.forEach.call(campo.files, function (arquivo) {
            dados.append(campo.name, arquivo);
          });
          return;
        }

        // <select multiple>: `campo.value` devolve só a primeira opção, e a
        // faixa de produtos ficava sempre com um item só
        if (campo.multiple && campo.tagName === 'SELECT') {
          Array.prototype.forEach.call(campo.selectedOptions, function (opcao) {
            dados.append(campo.name, opcao.value);
          });
          return;
        }

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

        // 413 vem do nginx como página HTML: tentar lê-la como JSON estourava
        // e o lojista via "verifique a conexão" para um arquivo grande demais
        if (resposta.status === 413) {
          toast('Arquivo grande demais para enviar. Comprima e tente de novo.', 'error');
          return;
        }
        const tipo = resposta.headers.get('content-type') || '';
        if (!tipo.includes('application/json')) {
          toast(
            resposta.ok
              ? 'Resposta inesperada do servidor. Recarregue a página.'
              : 'O servidor recusou o envio (erro ' + resposta.status + ').',
            'error'
          );
          return;
        }

        const json = await resposta.json();

        if (json.ok) {
          toast(json.criado ? 'Produto cadastrado!' : 'Produto atualizado!', 'success');
          fecharModal();
          setTimeout(function () { window.location.reload(); }, 700);
          return;
        }

        // devolve o formulário com os erros, sem perder o que já foi digitado
        $('[data-modal-corpo]').innerHTML = json.html;
        recarregado = true;
        toast('Confira os campos destacados.', 'error');
      } catch (erro) {
        toast('Não consegui salvar. Verifique a conexão.', 'error');
      } finally {
        btSalvar.classList.remove('is-loading');
        btSalvar.innerHTML = textoOriginal;
      }

      if (recarregado) prepararWizard();
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
    iniciarCamposImagem();
    iniciarAbas();
    iniciarPreviaAparencia();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', iniciar);
  } else {
    iniciar();
  }
})();
