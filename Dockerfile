# U-CS 37 — budget-forecast
#
# Three changes from the skeleton's version, each needed to deploy rather than
# merely to run locally:
#
#   The port comes from $PORT. Render, Cloud Run and most managed hosts assign
#   a port and inject it; a container listening on a hardcoded 8000 fails the
#   platform's health check and is killed. Note the shell form of CMD — the
#   exec form does not expand environment variables, so ["uvicorn", ...,
#   "$PORT"] passes the literal string "$PORT" to uvicorn. The shell then
#   `exec`s uvicorn so that it, not sh, receives SIGTERM.
#
#   A non-root user. Nothing here needs root after the dependencies are
#   installed, and a service reachable from the internet should not run as it.
#
#   A HEALTHCHECK, so `docker ps` reports whether the service is actually
#   answering rather than merely running.
#
# Build context is controlled by .dockerignore, which keeps .env, venv/ and the
# test suite out of the image.

FROM python:3.11-slim

# Fail fast and log immediately: without PYTHONUNBUFFERED, uvicorn's output is
# buffered and a crash loop on a hosting platform shows an empty log.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# Dependencies first, so a code change does not re-run pip on every build.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --create-home --shell /bin/false forecast \
    && chown -R forecast:forecast /app
USER forecast

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request; \
urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",8000)}/health').read()"

# `exec` replaces the shell with uvicorn, so uvicorn is PID 1 and receives the
# SIGTERM that `docker stop` and a host redeploy send. Without it sh is PID 1,
# does not forward the signal, and the container is SIGKILLed after the grace
# period (exit 137) instead of shutting down cleanly.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
