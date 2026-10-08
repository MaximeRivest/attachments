# attachments API server — production image for api.attachments.dev
#
# Build (from the REPO ROOT, so dist/ is in context):
#   rm -rf dist && uv build --wheel           # exactly one dist/attachments-*.whl
#   docker build -f deploy/Dockerfile -t attachments-api .
#
# Built and tested with Podman 5 on amd64 (2026-10-08): 1.72 GB, of which
# LibreOffice is 0.42 GB (1.30 GB without it). Tested in the running
# container: .doc/.odt/.ppt/.odp/.ods over POST /process (1.4-1.9 s each), 6
# parallel conversions (peak 365 MB), a hung conversion killed with all its
# child processes, and a client without LibreOffice falling back to it.
# Base images are fully qualified (docker.io/...) so Podman resolves them.

FROM docker.io/library/python:3.12-slim

# curl: HEALTHCHECK. libgl/glib: onnxruntime/opencv runtime libs used by
# rapidocr. tini: PID 1 that reaps processes LibreOffice leaves behind.
# LibreOffice (writer/impress/calc, no GUI): .doc/.ppt/.odt/.odp/.ods.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl libgl1 libglib2.0-0 tini \
        libreoffice-writer-nogui libreoffice-impress-nogui libreoffice-calc-nogui \
    && rm -rf /var/lib/apt/lists/*

# --- Install attachments[server] from the LOCAL wheel (pre-publish) -------
# Any one wheel in dist/ (WHEEL overrides the pattern). Fails clearly when
# dist/ holds zero or several wheels.
ARG WHEEL=dist/attachments-*.whl
COPY ${WHEEL} /tmp/
RUN set -- /tmp/attachments-*.whl \
    && if [ "$#" -ne 1 ] || [ ! -f "$1" ]; then \
         echo "expected exactly one attachments wheel in dist/, found: $*" >&2; exit 1; \
       fi \
    && pip install --no-cache-dir "$1[server]" gunicorn \
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

# A conversion must end before gunicorn's 120 s worker timeout; otherwise the
# worker is killed first and LibreOffice is left running.
ENV ATTACHMENTS_LIBREOFFICE_TIMEOUT=60

# Bake the OCR model download into the image so containers start warm even
# on a fresh host (rapidocr fetches its ONNX models on first use). --strict:
# the build fails if OCR or LibreOffice conversion does not work.
RUN python /app/warmup.py --strict

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# WEB_CONCURRENCY: standard gunicorn knob, set per instance size in compose.
# --preload imports wsgi.py (and runs warmup) ONCE in the master; workers
# inherit the warm processor imports + ONNX session via fork.
ENV WEB_CONCURRENCY=2
ENTRYPOINT ["tini", "--"]
CMD ["gunicorn", "wsgi:app", \
     "--bind", "0.0.0.0:8000", \
     "--preload", \
     "--timeout", "120", \
     "--graceful-timeout", "30", \
     "--max-requests", "500", \
     "--max-requests-jitter", "50", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
