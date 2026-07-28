# syntax=docker/dockerfile:1.9

# ==========================================
# STAGE 1: Builder
# ==========================================
FROM python:3.12-slim AS build

# Use strict error handling
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install uv (The builder needs it, the runner does not)
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /uvx /bin/

# UV Settings for optimal build
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
# Note: Removed UV_PYTHON_DOWNLOADS=never since we are using the base python image anyway
ENV workdir=/app
WORKDIR $workdir

RUN apt-get update -y
RUN apt-get install -y openssl ca-certificates
# WeasyPrint runtime libraries (HTML -> PDF for chat exports) and the fonts the chat template
# resolves against. Kept in the cached prefix, before the source COPY, so a xcode change does not
# re-run apt against a stale package index.
RUN apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-liberation fonts-dejavu-core
RUN apt-get install -y libffi-dev build-essential libssl-dev git rustc cargo

COPY uv.lock pyproject.toml $workdir/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev


COPY . $workdir
# Install the application into the venv
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

RUN rm -rf /root/.cargo

RUN apt-get remove --purge -y libffi-dev build-essential libssl-dev git rustc cargo



# ==========================================
# STAGE 2: Runner (Production) - Debian Slim
# ==========================================
FROM python:3.12-slim

ENV workdir=/app

# 1. Add venv to PATH
ENV PATH="${workdir}/.venv/bin:${PATH}"
ENV PYTHONPATH="${workdir}"

# 2. Python Security & Performance
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus

WORKDIR $workdir

# 3. Install runtime dependencies via apt-get
# Note: musl-dev is removed because Debian uses glibc
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    make \
    libffi8 \
    libatomic1 \
    libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-liberation fonts-dejavu-core \ 
    && rm -rf /var/lib/apt/lists/* \
    && git config --system --add safe.directory /app

# 4. Create non-root user (Debian style)
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -m appuser

# 5. Copy Application with Correct Permissions
COPY --from=build --chown=10001:10001 /app /app

# 6. Explicitly set non-root user
USER 10001:10001

# 7. Add Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/version || exit 1
