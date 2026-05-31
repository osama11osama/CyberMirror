# CyberMirror — multi-stage Docker (backend + static UI)
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS backend
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt \
    && playwright install chromium --with-deps || true
COPY backend/ ./backend/
COPY --from=frontend-build /app/frontend/dist/cybermirror/browser ./frontend/dist
ENV PYTHONUNBUFFERED=1
EXPOSE 8787
CMD ["python", "backend/main.py"]
