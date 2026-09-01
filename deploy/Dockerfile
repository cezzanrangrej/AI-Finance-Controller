# Multi-stage Dockerfile for AI Finance Controller

# Stage 1: Build Frontend Artifacts
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Production Python Backend Runtime
FROM python:3.12-slim AS runner
WORKDIR /app

# Prevent Python from writing bytecode and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy backend requirements and install dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source code and scripts
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY data/ ./data/

# Copy built frontend static assets from builder stage
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Expose FastAPI server port
EXPOSE 8000

# Run Uvicorn ASGI server
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
