# AgroCampo — imagem de produção.
#
# Build em dois estágios: as dependências de compilação (gcc, headers do
# Postgres) ficam no primeiro e não vão para a imagem final.
FROM python:3.12-slim AS build

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN python -m venv /venv \
    && /venv/bin/pip install --upgrade pip \
    && /venv/bin/pip install -r requirements.txt


# ---------------------------------------------------------------- runtime
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=config.settings

# libpq5 é o runtime do Postgres; curl serve ao healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
      libpq5 curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --create-home --uid 1000 agrocampo

COPY --from=build /venv /venv

WORKDIR /app
COPY --chown=agrocampo:agrocampo . .

# media e staticfiles são volumes em runtime; criados aqui com o dono certo
RUN mkdir -p /app/media /app/staticfiles \
    && chown -R agrocampo:agrocampo /app/media /app/staticfiles \
    && chmod +x /app/deploy/entrypoint.sh

USER agrocampo
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/api/v1/catalogo/categorias/ >/dev/null || exit 1

ENTRYPOINT ["/app/deploy/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--timeout", "60", \
     "--graceful-timeout", "30", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
