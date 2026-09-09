FROM python:3.14-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive

# Toolchain paths
ENV PATH="/opt/flutter/bin:/opt/flutter/bin/cache/dart-sdk/bin:/usr/local/go/bin:/root/.cargo/bin:/opt/venv/bin:${PATH}"

# ------------------------------------------------------------
# System dependencies
# ------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    wget \
    unzip \
    xz-utils \
    zip \
    ca-certificates \
    build-essential \
    clang \
    cmake \
    ninja-build \
    pkg-config \
    libglu1-mesa \
    && rm -rf /var/lib/apt/lists/*

# ------------------------------------------------------------
# Flutter + Dart
# ------------------------------------------------------------
RUN git clone --depth 1 --branch stable \
    https://github.com/flutter/flutter.git \
    /opt/flutter \
    && flutter config --no-analytics \
    && dart --disable-analytics \
    && flutter precache --no-web

# ------------------------------------------------------------
# Node.js 22
# ------------------------------------------------------------
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get update \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# ------------------------------------------------------------
# Go
# ------------------------------------------------------------
ARG TARGETARCH

RUN set -eux; \
    case "${TARGETARCH}" in \
        amd64) GOARCH="amd64" ;; \
        arm64) GOARCH="arm64" ;; \
        *) echo "Unsupported architecture: ${TARGETARCH}"; exit 1 ;; \
    esac; \
    wget -q "https://go.dev/dl/go1.25.1.linux-${GOARCH}.tar.gz"; \
    tar -C /usr/local -xzf "go1.25.1.linux-${GOARCH}.tar.gz"; \
    rm "go1.25.1.linux-${GOARCH}.tar.gz"

# ------------------------------------------------------------
# Rust
# ------------------------------------------------------------
RUN curl --proto '=https' \
    --tlsv1.2 \
    -sSf https://sh.rustup.rs \
    | sh -s -- -y --profile minimal

# ------------------------------------------------------------
# Python dependencies
# ------------------------------------------------------------
WORKDIR /app

COPY requirements.txt .

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# ------------------------------------------------------------
# Application
# ------------------------------------------------------------
COPY . .

EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]