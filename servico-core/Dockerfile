# Uma imagem para a central e para a borda; o papel vem de PAPEL (ADR-0006).
# Contexto de build: raiz do repositório (precisa de contratos/).
#   docker build -f servico-core/Dockerfile -t plataforma-iot/servico-core:dev .

FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore
WORKDIR /app
COPY servico-core/requirements.txt .
RUN pip install -r requirements.txt

# Testes e validação de contratos: docker compose -f servico-core/compose.testes.yaml run --rm testes
FROM base AS testes
COPY servico-core/requirements-dev.txt .
RUN pip install -r requirements-dev.txt
COPY contratos/ /app/contratos/
COPY servico-core/ /app/
CMD ["pytest", "--cov", "--cov-fail-under=70"]

FROM base AS final
COPY contratos/ /app/contratos/
COPY servico-core/configuracao.py servico-core/principal.py /app/
COPY servico-core/dominio/ /app/dominio/
COPY servico-core/portas/ /app/portas/
COPY servico-core/adaptadores/ /app/adaptadores/
RUN useradd --uid 10001 --no-create-home app
USER app
EXPOSE 8000
CMD ["uvicorn", "principal:criar_aplicacao", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
