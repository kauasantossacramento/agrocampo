/**
 * Serviço de WhatsApp Web para o AgroCampo.
 *
 * Mantém UMA sessão do WhatsApp Web viva (whatsapp-web.js + Chromium) e
 * expõe três rotas para o Django, todas protegidas por token:
 *
 *   GET  /status        estado da sessão + QR Code (data URL) quando precisa parear
 *   POST /enviar        { numero: "5575999990000", texto: "..." }
 *   POST /desconectar   encerra a sessão e apaga o pareamento
 *
 * AVISO: isto não é a API oficial da Meta. Controlar o WhatsApp Web por
 * robô viola os Termos de Serviço e o número pode ser banido. O lojista
 * optou por este caminho ciente do risco; o painel repete o aviso.
 *
 * Nunca publique este serviço na internet: ele só responde na rede interna
 * do compose e o token é a única barreira.
 */
const express = require("express");
const qrcode = require("qrcode");
const { Client, LocalAuth } = require("whatsapp-web.js");

const PORTA = Number(process.env.PORTA || 3000);
const TOKEN = process.env.WHATSAPP_WEB_TOKEN || "";
const PASTA_SESSAO = process.env.PASTA_SESSAO || "/dados";

if (!TOKEN) {
  console.error("[whatsapp] WHATSAPP_WEB_TOKEN vazio — recusando subir sem proteção.");
  process.exit(1);
}

// ------------------------------------------------------------ estado
let estado = "iniciando"; // iniciando | aguardando_qr | autenticando | conectado | desconectado | erro
let qrAtual = null;       // data URL do QR, só enquanto aguardando_qr
let detalhe = "";
let numero = "";

const client = new Client({
  authStrategy: new LocalAuth({ dataPath: PASTA_SESSAO }),
  puppeteer: {
    headless: true,
    executablePath: process.env.CHROMIUM_PATH || undefined,
    args: [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-dev-shm-usage",
      "--disable-gpu",
      "--no-zygote",
      "--single-process",
    ],
  },
});

client.on("qr", async (qr) => {
  estado = "aguardando_qr";
  detalhe = "Abra o WhatsApp no celular › Aparelhos conectados › Conectar aparelho.";
  try {
    qrAtual = await qrcode.toDataURL(qr, { margin: 1, width: 280 });
  } catch (e) {
    qrAtual = null;
    detalhe = "Falha ao gerar o QR: " + e.message;
  }
  console.log("[whatsapp] QR gerado — aguardando leitura");
});

client.on("authenticated", () => {
  estado = "autenticando";
  qrAtual = null;
  detalhe = "Pareado. Carregando conversas…";
});

client.on("ready", () => {
  estado = "conectado";
  qrAtual = null;
  detalhe = "";
  numero = client.info && client.info.wid ? client.info.wid.user : "";
  console.log("[whatsapp] conectado como", numero || "(número desconhecido)");
});

client.on("auth_failure", (msg) => {
  estado = "erro";
  qrAtual = null;
  detalhe = "Falha de autenticação: " + msg;
  console.error("[whatsapp] auth_failure", msg);
});

client.on("disconnected", (motivo) => {
  estado = "desconectado";
  qrAtual = null;
  numero = "";
  detalhe = "Sessão encerrada: " + motivo;
  console.warn("[whatsapp] desconectado:", motivo);
  // tenta voltar sozinho; se o pareamento foi removido, cai em "qr" de novo
  setTimeout(() => client.initialize().catch(registrarErro), 5000);
});

function registrarErro(e) {
  estado = "erro";
  detalhe = e && e.message ? e.message : String(e);
  console.error("[whatsapp] erro:", detalhe);
}

client.initialize().catch(registrarErro);

// ------------------------------------------------------------- http
const app = express();
app.use(express.json({ limit: "64kb" }));

app.use((req, res, next) => {
  const auth = req.get("authorization") || "";
  if (auth !== `Bearer ${TOKEN}`) {
    return res.status(401).json({ erro: "token inválido" });
  }
  next();
});

app.get("/status", (_req, res) => {
  res.json({ estado, qr: qrAtual, detalhe, numero });
});

app.post("/enviar", async (req, res) => {
  const { numero: destino, texto } = req.body || {};
  const digitos = String(destino || "").replace(/\D/g, "");
  if (!digitos || !texto) {
    return res.status(400).json({ erro: "informe numero e texto" });
  }
  if (estado !== "conectado") {
    return res.status(503).json({ erro: `sessão ${estado}` });
  }
  try {
    // getNumberId resolve o JID certo (o WhatsApp às vezes registra o
    // número sem o nono dígito) e devolve null se o número não tem conta
    const registro = await client.getNumberId(digitos);
    if (!registro) {
      return res.status(404).json({ erro: "número sem WhatsApp" });
    }
    await client.sendMessage(registro._serialized, String(texto));
    res.json({ ok: true });
  } catch (e) {
    console.error("[whatsapp] falha ao enviar:", e.message);
    res.status(500).json({ erro: e.message });
  }
});

app.post("/desconectar", async (_req, res) => {
  try {
    await client.logout();
    estado = "desconectado";
    qrAtual = null;
    numero = "";
    detalhe = "Desconectado pelo painel.";
    res.json({ ok: true });
  } catch (e) {
    res.status(500).json({ erro: e.message });
  }
});

app.listen(PORTA, "0.0.0.0", () => {
  console.log(`[whatsapp] ouvindo em :${PORTA}, sessão em ${PASTA_SESSAO}`);
});
