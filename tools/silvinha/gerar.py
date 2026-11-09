"""Motor de imagens da Silvinha: gera, confere e gera de novo.

Fluxo, em duas etapas:

1. **referencia** — a partir das fotos da proprietária (pasta `referencias/`),
   gera a folha de personagem: ela de frente, de uniforme, no estilo
   escolhido. É o que amarra todas as poses ao mesmo rosto e à mesma roupa.
2. **poses** — cada pose do `silvinha.json` é gerada usando as fotos E a
   folha aprovada como referência.

Cada imagem passa por duas conferências antes de ser aceita:

* **local**, nos pixels: fundo transparente, corpo cortado na borda certa
  ("saindo de baixo" precisa encostar na borda inferior), lado vazio para o
  balão de fala;
* **avaliador** (modelo de visão da OpenAI): semelhança com o rosto das
  fotos, pose pedida, consistência com a folha, mãos com cinco dedos e
  nenhum texto na imagem.

Reprovada, a imagem é gerada de novo com a correção que o avaliador
escreveu, até `--tentativas`. Todas as tentativas ficam em `saida/<pose>/`;
a melhor vira `saida/<pose>.png`. Os balões de fala NÃO são desenhados na
imagem: texto em imagem gerada sai torto e não dá para trocar a frase. O
site desenha o balão no espaço vazio que cada pose deixa.

Uso (da raiz do projeto, com o .venv):
    python tools/silvinha/gerar.py verificar
    python tools/silvinha/gerar.py referencia
    python tools/silvinha/gerar.py poses [avatar acenando ...]
    python tools/silvinha/gerar.py avaliar saida/acenando.png --pose acenando

A chave fica em tools/silvinha/.env (OPENAI_API_KEY=...), fora do Git.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
import time
from pathlib import Path

import requests
from PIL import Image

PASTA = Path(__file__).resolve().parent
ESCOPO = json.loads((PASTA / "silvinha.json").read_text(encoding="utf-8"))
REFERENCIAS = PASTA / "referencias"
SAIDA = PASTA / "saida"
API = "https://api.openai.com/v1"
EXTENSOES_FOTO = {".jpg", ".jpeg", ".png", ".webp"}
MAX_FOTOS = 6          # fotos da proprietária enviadas por geração
LADO_FOTO = 1536       # lado máximo da foto enviada: mais que isso só pesa


# ───────────────────────────────────────────────────────── infraestrutura
def _chave() -> str:
    chave = os.environ.get("OPENAI_API_KEY", "")
    arquivo = PASTA / ".env"
    if not chave and arquivo.exists():
        for linha in arquivo.read_text(encoding="utf-8").splitlines():
            if linha.startswith("OPENAI_API_KEY="):
                chave = linha.split("=", 1)[1].strip()
    if not chave:
        sys.exit("Falta OPENAI_API_KEY em tools/silvinha/.env")
    return chave


def _cabecalho() -> dict:
    return {"Authorization": f"Bearer {_chave()}"}


def _erro(resposta) -> str:
    try:
        return resposta.json()["error"]["message"]
    except Exception:
        return resposta.text[:300]


def _png(imagem: Image.Image) -> bytes:
    saida = io.BytesIO()
    imagem.save(saida, format="PNG")
    return saida.getvalue()


def _foto_para_envio(caminho: Path) -> tuple[str, bytes, str]:
    """Foto reduzida e sem metadados — o EXIF de celular leva GPS junto."""
    imagem = Image.open(caminho)
    imagem = imagem.convert("RGBA" if imagem.mode in ("RGBA", "LA", "P") else "RGB")
    imagem.thumbnail((LADO_FOTO, LADO_FOTO), Image.LANCZOS)
    return (caminho.stem + ".png", _png(imagem), "image/png")


def fotos_da_proprietaria() -> list[Path]:
    if not REFERENCIAS.exists():
        return []
    return sorted(p for p in REFERENCIAS.iterdir() if p.suffix.lower() in EXTENSOES_FOTO)[:MAX_FOTOS]


# ─────────────────────────────────────────────────────────────── prompt
def montar_prompt(pedido: str, ajuste: str = "", com_fotos: bool = True,
                  com_folha: bool = False) -> str:
    p = ESCOPO["personagem"]
    partes = []
    if com_fotos:
        partes.append(p["identidade"])
    else:
        # só para testar o motor antes de as fotos chegarem
        partes.append("The character is a friendly Brazilian woman in her thirties "
                      "(placeholder for engine testing only).")
    if com_folha:
        partes.append("The LAST reference image is the approved character sheet: "
                      "keep exactly the same face, hair, art style and uniform as in it.")
    partes += [p["estilo"], p["roupa"], "POSE: " + pedido, p["regras"]]
    if ajuste:
        partes.append("CORRECTIONS FROM THE PREVIOUS ATTEMPT (must fix): " + ajuste)
    return "\n\n".join(partes)


# ───────────────────────────────────────────────────────────── geração
def gerar_imagem(prompt: str, tamanho: str, referencias: list[Path],
                 qualidade: str) -> tuple[Image.Image, dict]:
    modelo = ESCOPO["modelos"]["imagem"]
    comum = {"model": modelo, "prompt": prompt, "size": tamanho, "quality": qualidade,
             "background": "transparent", "output_format": "png"}
    if referencias:
        arquivos = [("image[]", _foto_para_envio(r)) for r in referencias]
        resposta = requests.post(f"{API}/images/edits", headers=_cabecalho(),
                                 data=comum, files=arquivos, timeout=600)
    else:
        resposta = requests.post(f"{API}/images/generations", headers=_cabecalho(),
                                 json=comum, timeout=600)
    if resposta.status_code >= 400:
        raise RuntimeError(f"geração recusada ({resposta.status_code}): {_erro(resposta)}")
    dados = resposta.json()
    imagem = Image.open(io.BytesIO(base64.b64decode(dados["data"][0]["b64_json"])))
    return imagem.convert("RGBA"), dados.get("usage", {})


# ─────────────────────────────────────────────────── conferência local
def _opaco(faixa: Image.Image) -> float:
    """Fração de pixels visíveis (alfa > 40) numa faixa da imagem."""
    alfa = faixa.getchannel("A")
    visiveis = sum(alfa.histogram()[41:])
    return visiveis / max(1, alfa.width * alfa.height)


def conferir_pixels(imagem: Image.Image, checagens: dict) -> list[str]:
    """Problemas que dá para medir sem olhar: transparência e bordas."""
    problemas = []
    w, h = imagem.size
    alfa_min = imagem.getchannel("A").getextrema()[0]
    if alfa_min > 0:
        return ["o fundo não saiu transparente"]

    faixa = max(4, h // 60)
    borda = {
        "superior": imagem.crop((0, 0, w, faixa)),
        "inferior": imagem.crop((0, h - faixa, w, h)),
    }
    if checagens.get("cantos_transparentes"):
        lado = max(8, w // 12)
        for nome, caixa in (("superior esquerdo", (0, 0, lado, lado)),
                            ("superior direito", (w - lado, 0, w, lado))):
            if _opaco(imagem.crop(caixa)) > 0.05:
                problemas.append(f"o canto {nome} deveria estar vazio")

    ocupada = checagens.get("borda_ocupada")
    if ocupada and _opaco(borda[ocupada]) < 0.15:
        problemas.append(
            f"o corpo deveria ser cortado pela borda {ocupada} (está solto no meio)"
        )
    vazia = checagens.get("borda_vazia")
    if vazia and _opaco(borda[vazia]) > 0.02:
        problemas.append(f"a borda {vazia} deveria ficar vazia")

    lado_vazio = checagens.get("lado_vazio")
    if lado_vazio:
        terco = w // 3
        caixa = (w - terco, 0, w, h) if lado_vazio == "direita" else (0, 0, terco, h)
        if _opaco(imagem.crop(caixa)) > 0.12:
            problemas.append(f"o lado {lado_vazio} deveria ficar livre para o balão")
    return problemas


# ───────────────────────────────────────────────────────────── avaliador
ESQUEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "semelhanca_rosto": {"type": "integer", "description": "0-10; 10 se não houver fotos"},
        "pose": {"type": "integer", "description": "0-10, o quanto a pose pedida foi seguida"},
        "consistencia": {"type": "integer", "description": "0-10 com a folha de personagem; 10 se não houver folha"},
        "estilo": {"type": "integer", "description": "0-10, o quanto segue o estilo pedido (ilustração, não foto)"},
        "maos_ok": {"type": "boolean"},
        "sem_texto": {"type": "boolean"},
        "problemas": {"type": "array", "items": {"type": "string"}},
        "correcao_em_ingles": {"type": "string",
                               "description": "instrução curta para o gerador corrigir na próxima tentativa"},
    },
    "required": ["semelhanca_rosto", "pose", "consistencia", "estilo", "maos_ok", "sem_texto",
                 "problemas", "correcao_em_ingles"],
}


def _data_url(imagem: Image.Image, lado: int = 768) -> str:
    # transparente vira cinza claro: o avaliador enxerga o recorte e as bordas
    copia = imagem.copy()
    copia.thumbnail((lado, lado), Image.LANCZOS)
    if copia.mode == "RGBA":
        fundo = Image.new("RGBA", copia.size, (232, 232, 232, 255))
        fundo.alpha_composite(copia)
        copia = fundo.convert("RGB")
    saida = io.BytesIO()
    copia.convert("RGB").save(saida, format="JPEG", quality=88)
    return "data:image/jpeg;base64," + base64.b64encode(saida.getvalue()).decode()


def avaliar(imagem: Image.Image, criterios: str, fotos: list[Path],
            folha: Path | None) -> dict:
    conteudo = [{"type": "input_text", "text": (
        "Você confere imagens geradas da Silvinha, mascote da loja AgroCampo. Cada "
        "imagem a seguir vem precedida de um rótulo dizendo o que ela é. Na imagem "
        "AVALIADA, o cinza claro liso é o FUNDO TRANSPARENTE desenhado para você "
        "enxergar o recorte — a transparência já foi conferida nos pixels: NÃO avalie "
        "nem cite o fundo. Seja exigente com o resto.\n\n"
        f"Pose pedida: {criterios}\n"
        f"Estilo pedido: {ESCOPO['personagem']['estilo']}\n"
        f"Escopo do personagem: {ESCOPO['personagem']['roupa']} {ESCOPO['personagem']['regras']}\n\n"
        "Notas de 0 a 10: semelhança do rosto com as fotos (formato do rosto, olhos, "
        "nariz, boca, cabelo, tom de pele), pose, consistência com a folha e estilo — "
        "uma imagem que parece FOTO quando o pedido é ilustração leva nota baixa de estilo. Marque "
        "maos_ok=false se houver dedo a mais/a menos ou mão deformada, e sem_texto=false "
        "se houver qualquer letra, logo ou balão desenhado. Em correcao_em_ingles, escreva "
        "o que o gerador deve mudar para acertar."
    )}]
    # rótulo antes de cada imagem: sem fotos, o avaliador tomava a folha de
    # personagem por foto e dizia que a folha não tinha vindo
    if not fotos:
        conteudo.append({"type": "input_text", "text": "Não há fotos reais nesta avaliação: dê 10 em semelhanca_rosto."})
    for n, foto in enumerate(fotos, 1):
        conteudo.append({"type": "input_text", "text": f"FOTO REAL {n} da pessoa (referência de rosto):"})
        conteudo.append({"type": "input_image", "image_url": _data_url(Image.open(foto).convert("RGB"))})
    if folha and folha.exists():
        conteudo.append({"type": "input_text", "text": "FOLHA DE PERSONAGEM aprovada (referência de estilo, roupa e rosto):"})
        conteudo.append({"type": "input_image", "image_url": _data_url(Image.open(folha))})
    else:
        conteudo.append({"type": "input_text", "text": "Não há folha de personagem: dê 10 em consistencia."})
    conteudo.append({"type": "input_text", "text": "IMAGEM AVALIADA:"})
    conteudo.append({"type": "input_image", "image_url": _data_url(imagem)})

    resposta = requests.post(f"{API}/responses", headers=_cabecalho(), timeout=300, json={
        "model": ESCOPO["modelos"]["avaliador"],
        "input": [{"role": "user", "content": conteudo}],
        "text": {"format": {"type": "json_schema", "name": "avaliacao",
                            "schema": ESQUEMA, "strict": True}},
    })
    if resposta.status_code >= 400:
        raise RuntimeError(f"avaliador recusou ({resposta.status_code}): {_erro(resposta)}")
    dados = resposta.json()
    texto = next(
        c["text"] for item in dados.get("output", []) if item.get("type") == "message"
        for c in item.get("content", []) if c.get("type") == "output_text"
    )
    return json.loads(texto)


def aprovada(avaliacao: dict, problemas_locais: list[str], com_fotos: bool) -> bool:
    minimo = ESCOPO["aprovacao"]["nota_minima"]
    return (
        not problemas_locais
        and avaliacao["pose"] >= minimo
        and avaliacao["consistencia"] >= minimo
        and avaliacao["estilo"] >= ESCOPO["aprovacao"].get("nota_minima_estilo", minimo)
        and (avaliacao["semelhanca_rosto"] >= minimo or not com_fotos)
        and avaliacao["maos_ok"] and avaliacao["sem_texto"]
    )


def _nota(avaliacao: dict, problemas_locais: list[str]) -> float:
    base = (avaliacao["semelhanca_rosto"] * 2 + avaliacao["pose"]
            + avaliacao["consistencia"] + avaliacao["estilo"]) / 5
    return base - 2 * len(problemas_locais) - (0 if avaliacao["maos_ok"] else 2) \
        - (0 if avaliacao["sem_texto"] else 3)


# ───────────────────────────────────────────── uma pose, até dar certo
def produzir(nome: str, pedido: str, criterios: str, tamanho: str, checagens: dict,
             tentativas: int, qualidade: str, usar_folha: bool) -> Path | None:
    fotos = fotos_da_proprietaria()
    folha = SAIDA / "referencia.png"
    referencias = list(fotos)
    if usar_folha and folha.exists():
        referencias.append(folha)
    pasta = SAIDA / nome
    pasta.mkdir(parents=True, exist_ok=True)

    melhor, melhor_nota, ajuste = None, -99.0, ""
    for n in range(1, tentativas + 1):
        prompt = montar_prompt(pedido, ajuste, com_fotos=bool(fotos),
                               com_folha=usar_folha and folha.exists())
        print(f"[{nome}] tentativa {n}/{tentativas} · {len(referencias)} referências · {qualidade}…", flush=True)
        inicio = time.monotonic()
        try:
            imagem, uso = gerar_imagem(prompt, tamanho, referencias, qualidade)
        except RuntimeError as exc:
            print(f"  ✗ {exc}")
            if "safety" in str(exc).lower() or "moderation" in str(exc).lower():
                return melhor
            continue
        arquivo = pasta / f"tentativa-{n}.png"
        imagem.save(arquivo)

        locais = conferir_pixels(imagem, checagens)
        avaliacao = avaliar(imagem, criterios, fotos, folha if usar_folha else None)
        nota = _nota(avaliacao, locais)
        ok = aprovada(avaliacao, locais, bool(fotos))
        (pasta / f"tentativa-{n}.json").write_text(json.dumps({
            "prompt": prompt, "uso": uso, "segundos": round(time.monotonic() - inicio),
            "problemas_locais": locais, "avaliacao": avaliacao, "nota": nota, "aprovada": ok,
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  rosto {avaliacao['semelhanca_rosto']} · pose {avaliacao['pose']} · "
              f"consistência {avaliacao['consistencia']} · estilo {avaliacao['estilo']} · mãos {'ok' if avaliacao['maos_ok'] else 'NÃO'} · "
              f"texto {'não' if avaliacao['sem_texto'] else 'SIM'} · nota {nota:.1f} → "
              f"{'APROVADA' if ok else 'refazer'}")
        for problema in locais + avaliacao["problemas"]:
            print(f"    - {problema}")

        if nota > melhor_nota:
            melhor, melhor_nota = arquivo, nota
        if ok:
            break
        ajuste = "; ".join(locais + [avaliacao["correcao_em_ingles"]])

    if melhor:
        destino = SAIDA / f"{nome}.png"
        Image.open(melhor).save(destino)
        print(f"[{nome}] fica a {melhor.name} (nota {melhor_nota:.1f}) → {destino}")
        return destino
    return None


# ──────────────────────────────────────────────────────────── comandos
def cmd_verificar(_):
    r = requests.get(f"{API}/models", headers=_cabecalho(), timeout=30)
    if r.status_code >= 400:
        sys.exit(f"Chave recusada: {_erro(r)}")
    ids = {m["id"] for m in r.json()["data"]}
    for papel, modelo in (("imagem", ESCOPO["modelos"]["imagem"]),
                          ("avaliador", ESCOPO["modelos"]["avaliador"])):
        print(f"{papel:10} {modelo:28} {'disponível' if modelo in ids else 'NÃO disponível nesta conta'}")
    fotos = fotos_da_proprietaria()
    print(f"fotos em referencias/: {len(fotos)}" + ("" if fotos else " — envie as fotos da proprietária"))
    print(f"folha de personagem: {'aprovada' if (SAIDA / 'referencia.png').exists() else 'ainda não gerada'}")


def cmd_referencia(a):
    if not fotos_da_proprietaria() and not a.sem_fotos:
        sys.exit("Coloque as fotos da proprietária em tools/silvinha/referencias/ "
                 "(ou use --sem-fotos só para testar o motor).")
    f = ESCOPO["folha_de_personagem"]
    produzir(f["nome"], f["prompt"], "Retrato de referência: em pé, de frente, dos joelhos para "
             "cima, braços relaxados, sorriso leve, rosto e uniforme bem iluminados.",
             f["tamanho"], {"cantos_transparentes": True}, a.tentativas, a.qualidade,
             usar_folha=False)
    # de onde veio a folha: a de teste (sem fotos) não pode virar referência
    # das poses de verdade por engano
    (SAIDA / "referencia.origem.json").write_text(json.dumps({
        "fotos": [p.name for p in fotos_da_proprietaria()],
    }, ensure_ascii=False), encoding="utf-8")


def cmd_poses(a):
    poses = ESCOPO["poses"]
    if a.nomes:
        poses = [p for p in poses if p["nome"] in a.nomes]
        faltando = set(a.nomes) - {p["nome"] for p in poses}
        if faltando:
            sys.exit(f"Pose desconhecida: {', '.join(sorted(faltando))}")
    if not (SAIDA / "referencia.png").exists() and not a.sem_folha:
        sys.exit("Gere e aprove primeiro a folha de personagem: gerar.py referencia")
    origem = SAIDA / "referencia.origem.json"
    fotos_da_folha = json.loads(origem.read_text(encoding="utf-8"))["fotos"] if origem.exists() else []
    if fotos_da_proprietaria() and not fotos_da_folha and not a.sem_folha:
        sys.exit("A folha de personagem atual foi feita SEM as fotos (era teste). "
                 "Gere a de verdade antes: gerar.py referencia")
    for pose in poses:
        produzir(pose["nome"], pose["prompt"], pose["criterios"], pose["tamanho"],
                 pose.get("checagens", {}), a.tentativas, a.qualidade, usar_folha=not a.sem_folha)


def cmd_avaliar(a):
    pose = next((p for p in ESCOPO["poses"] if p["nome"] == a.pose), None)
    if not pose:
        sys.exit(f"Pose desconhecida: {a.pose}")
    imagem = Image.open(a.arquivo).convert("RGBA")
    locais = conferir_pixels(imagem, pose.get("checagens", {}))
    avaliacao = avaliar(imagem, pose["criterios"], fotos_da_proprietaria(), SAIDA / "referencia.png")
    print(json.dumps({"problemas_locais": locais, **avaliacao}, ensure_ascii=False, indent=1))


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="comando", required=True)
    sub.add_parser("verificar").set_defaults(func=cmd_verificar)
    for nome, func in (("referencia", cmd_referencia), ("poses", cmd_poses)):
        s = sub.add_parser(nome)
        s.add_argument("--tentativas", type=int, default=3)
        s.add_argument("--qualidade", choices=["low", "medium", "high"], default="high")
        s.set_defaults(func=func)
        if nome == "poses":
            s.add_argument("nomes", nargs="*")
            s.add_argument("--sem-folha", action="store_true", help="não usa a folha de personagem")
        else:
            s.add_argument("--sem-fotos", action="store_true", help="testa o motor sem as fotos")
    s = sub.add_parser("avaliar")
    s.add_argument("arquivo")
    s.add_argument("--pose", required=True)
    s.set_defaults(func=cmd_avaliar)
    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
