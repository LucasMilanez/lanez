FROM python:3.12-slim

RUN useradd --create-home --shell /bin/bash lanez

WORKDIR /app

COPY --chown=lanez:lanez requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=lanez:lanez . .

USER lanez

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz', timeout=3)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
