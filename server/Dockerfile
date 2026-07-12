# ── VisionShield backend ─────────────────────────────────────────────
# MediaPipe's libmediapipe.so links against libGLESv2 + libEGL (+ their
# libglvnd0/libegl-mesa0 deps, pulled in automatically) even when running
# CPU-only / headless — ldd libmediapipe.so to re-verify if this changes.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libgles2 libegl1 libglib2.0-0 \
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