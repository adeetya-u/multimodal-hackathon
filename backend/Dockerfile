# Insforge Custom Compute / Fly.io — same image as Render
FROM ghcr.io/astral-sh/uv:python3.12-trixie-slim

ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1
ENV PYTHONPATH=/app
ENV PORT=8080

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ \
  && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY agents ./agents
COPY assets ./assets
COPY cases ./cases
COPY services ./services
COPY shared ./shared
COPY skills ./skills
COPY scripts ./scripts

RUN uv sync --no-dev

EXPOSE 8080

CMD ["sh", "-c", "uv run uvicorn services.api.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
