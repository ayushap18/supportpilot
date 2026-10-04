FROM node:22-bookworm-slim AS frontend
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
WORKDIR /app
ARG BUILD_SHA=development
ENV BUILD_SHA=$BUILD_SHA \
    SUPPORTPILOT_ROOT=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
RUN useradd --create-home --uid 10001 supportpilot
COPY requirements.lock pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.lock
COPY backend/ backend/
RUN pip install --no-deps --no-build-isolation .
COPY data/ data/
COPY scripts/ scripts/
COPY --from=frontend /web/dist/ frontend/dist/
RUN mkdir -p .state && chown -R supportpilot:supportpilot /app
USER supportpilot
EXPOSE 8000
CMD ["python", "scripts/serve.py"]
