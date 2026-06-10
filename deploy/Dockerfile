# attachments API server — production image for api.attachments.dev
#
# Build (from the REPO ROOT, so dist/ is in context):
#   uv build                                  # produces dist/attachments-*.whl
#   docker build -f deploy/Dockerfile -t attachments-api .
#
# NOTE: untested-build in this environment (no docker available where this
# file was authored). Validate with the build command above before launch.

FROM python:3.12-slim

# curl: HEALTHCHECK. libgl/glib: onnxruntime/opencv runtime libs used by
# rapidocr. Kept minimal on purpose.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# --- Install attachments[server] from the LOCAL wheel (pre-publish) -------
# The wheel filename is passed as a build arg so version bumps don't require
# editing this file: docker build --build-arg WHEEL=dist/attachments-1.0.0-py3-none-any.whl ...
ARG WHEEL=dist/attachments-1.0.0-py3-none-any.whl
COPY ${WHEEL} /tmp/
RUN pip install --no-cache-dir "$(ls /tmp/attachments-*.whl)[server]" gunicorn \
    && rm -f /tmp/attachments-*.whl

# --- PyPI alternative (post-publish): replace the three lines above with ---
# RUN pip install --no-cache-dir "attachments[server]==1.0.0" gunicorn

WORKDIR /app
COPY deploy/warmup.py deploy/wsgi.py /app/

# Security: never run as root.
RUN useradd -m -u 1000 attachments \
    && mkdir -p /home/attachments/.cache \
    && chown -R attachments:attachments /app /home/attachments
USER attachments
ENV HOME=/home/attachments

# Bake the OCR model download into the image so containers start warm even
# on a fresh host (rapidocr fetches its ONNX models on first use).
RUN python /app/warmup.py

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# WEB_CONCURRENCY: standard gunicorn knob, set per instance size in compose.
# --preload imports wsgi.py (and runs warmup) ONCE in the master; workers
# inherit the warm processor imports + ONNX session via fork.
ENV WEB_CONCURRENCY=2
CMD ["gunicorn", "wsgi:app", \
     "--bind", "0.0.0.0:8000", \
     "--preload", \
     "--timeout", "120", \
     "--graceful-timeout", "30", \
     "--max-requests", "500", \
     "--max-requests-jitter", "50", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
