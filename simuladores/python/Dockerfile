# Simuladores em Python: sensores rurais (MQTT na borda) e estação urbana legada (MQTT na central).
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_ROOT_USER_ACTION=ignore
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY simulador.py estacao_legada.py ./
USER nobody
CMD ["python", "simulador.py"]
