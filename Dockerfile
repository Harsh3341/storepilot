FROM node:24-alpine AS frontend
WORKDIR /app/frontend
RUN npm install --global pnpm@11.25.0
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --uid 10001 --create-home storepilot \
    && mkdir -p /app/data /app/backups \
    && chown -R storepilot:storepilot /app
COPY --chown=storepilot:storepilot storepilot/ ./storepilot/
COPY --chown=storepilot:storepilot data/catalogue.json ./data/catalogue.json
COPY --from=frontend --chown=storepilot:storepilot /app/frontend/dist/ ./frontend/dist/
USER storepilot
EXPOSE 8000
CMD ["sh", "-c", "exec python -m uvicorn storepilot.api:create_app --factory --host 0.0.0.0 --port ${PORT:-8000} --no-proxy-headers"]
