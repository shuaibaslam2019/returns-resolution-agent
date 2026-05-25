FROM --platform=linux/amd64 python:3.11-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml ./
RUN uv pip install --system azure-ai-agents azure-ai-projects azure-identity python-dotenv azure-monitor-opentelemetry fastapi uvicorn

COPY agents/ ./agents/
COPY data/ ./data/
COPY orchestrator.py .
COPY server.py .

EXPOSE 8080

CMD ["python", "server.py"]