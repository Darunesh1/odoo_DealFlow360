FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS base

# Prevent Python from writing pyc files and keep stdout/stderr unbuffered
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Install dependencies using cached mounts for maximum speed
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --frozen --no-install-project

# Put virtual environment on the PATH
ENV PATH="/app/.venv/bin:$PATH"

# Copy project files
COPY . .

# Default port
EXPOSE 8000

# Default command runs the FastAPI app.
# No --reload: this image is for deployment, local development runs natively.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
