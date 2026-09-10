# No `# syntax=` directive: everything used here (multi-stage, RUN --mount)
# is in BuildKit's built-in frontend, and pinning the external one makes the
# build fail wherever the daemon cannot reach docker.io to fetch it.

# Build the virtualenv in one stage and copy it into a clean runtime image, so
# uv and the build tooling never ship. Only the FastAPI deployment is
# supported here - the upstream PHP export path is not (see README).
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.9.17 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app

# Dependencies resolve from the lockfile alone, so this layer is cached until
# one of these two files changes - editing the app itself does not re-resolve.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --extra analyze --no-install-project

COPY listen_and_rate ./listen_and_rate
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --extra analyze


FROM python:3.12-slim AS runtime

# soundfile loads libsndfile through cffi at import time, so it has to be
# present in the runtime image even though pip installed nothing for it.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    LISTEN_AND_RATE_CONFIG=/app/data/json/config.yaml

WORKDIR /app
COPY listen_and_rate ./listen_and_rate
COPY frontend ./frontend

# Ratings are written into the bind-mounted data/ directory, so the process
# must not run as root - root-owned result files are awkward to collect from
# the host afterwards.
RUN useradd --create-home --uid 1000 app && chown -R app:app /app
USER app

EXPOSE 8000
CMD ["uvicorn", "listen_and_rate.main:app", "--host", "0.0.0.0", "--port", "8000"]
