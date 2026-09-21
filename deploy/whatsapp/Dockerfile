# Serviço de WhatsApp Web do AgroCampo. Usa o Chromium do Debian em vez do
# que o puppeteer baixaria: menor, com as fontes certas e sem surpresa de
# download no build.
FROM node:20-bookworm-slim

ENV PUPPETEER_SKIP_DOWNLOAD=true \
    CHROMIUM_PATH=/usr/bin/chromium \
    PASTA_SESSAO=/dados \
    NODE_ENV=production

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      chromium fonts-liberation fonts-noto-color-emoji ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev --no-audit --no-fund
COPY server.js ./

# roda sem root: o Chromium reclama menos e um vazamento não vira root
RUN useradd -r -m -d /home/whatsapp whatsapp && mkdir -p /dados && chown whatsapp:whatsapp /dados
USER whatsapp

VOLUME ["/dados"]
EXPOSE 3000
CMD ["node", "server.js"]
