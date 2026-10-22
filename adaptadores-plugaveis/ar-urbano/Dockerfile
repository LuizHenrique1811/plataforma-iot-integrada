# Adaptador plugável ar-urbano (RF-INT-03): imagem própria, sem código do núcleo.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_ROOT_USER_ACTION=ignore
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY traducao.py adaptador.py ./
RUN useradd --uid 10001 --no-create-home app
USER app
CMD ["python", "adaptador.py"]
