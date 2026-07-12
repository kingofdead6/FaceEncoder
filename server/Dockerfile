# ── VisionShield backend ─────────────────────────────────────────────
# python:3.11-slim keeps the image small; libgl1 + libglib2.0-0 are the
# only system libraries OpenCV needs at runtime.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first — this layer only rebuilds when requirements change.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY models ./models

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
