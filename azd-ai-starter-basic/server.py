"""
server.py
---------
FastAPI server wrapping the 3-agent pipeline.
Exposes /readiness, /health, /healthz endpoints for Azure probe checks.
Exposes /responses for the Hosted Agent protocol.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
load_dotenv()

import os
import json
import logging
from pathlib import Path

from azure.ai.agents import AgentsClient
from azure.identity import ManagedIdentityCredential

from agents.intake_agent import create_intake_agent, run_intake_agent
from agents.policy_agent import create_policy_agent, upload_policy_document, run_policy_agent
from agents.resolution_agent import create_resolution_agent, run_resolution_agent

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Load static data at startup
DATA_DIR = Path(__file__).parent / "data"

with open(DATA_DIR / "product_catalog.json") as f:
    catalog = json.load(f)

# ── Health / Readiness endpoints ───────────────────────────────────────────────

@app.get("/")
async def root():
    return JSONResponse({"status": "ready"}, status_code=200)

@app.get("/health")
async def health():
    return JSONResponse({"status": "healthy"}, status_code=200)

@app.get("/readiness")
async def readiness():
    return JSONResponse({"status": "ready"}, status_code=200)

@app.get("/healthz")
async def healthz():
    return JSONResponse({"status": "ok"}, status_code=200)

@app.get("/liveness")
async def liveness():
    return JSONResponse({"status": "alive"}, status_code=200)

# ── Main agent endpoint ────────────────────────────────────────────────────────

@app.post("/responses")
async def responses(request: Request):
    body = await request.json()
    user_input = body.get("input", "")
    logger.info(f"Received request: {user_input[:100]}")

    # Build return request from free text
    return_request = {
        "id": "RET-LIVE-001",
        "company": "Customer",
        "order_id": "ORD-LIVE",
        "product_sku": "UNKNOWN",
        "submitted_at": "2026-01-01T00:00:00Z",
        "free_text": user_input,
    }

    PROJECT_ENDPOINT = os.environ.get("AZURE_AI_PROJECT_ENDPOINT", "")
    MODEL_NAME = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4.1")

    if not PROJECT_ENDPOINT:
        logger.error("AZURE_AI_PROJECT_ENDPOINT not set")
        return JSONResponse(
            {"error": "AZURE_AI_PROJECT_ENDPOINT not configured"},
            status_code=500
        )

    try:
        client = AgentsClient(
            endpoint=PROJECT_ENDPOINT,
            credential=ManagedIdentityCredential(),
        )

        # Upload policy and create agents
        vector_store_id = upload_policy_document(
            client, str(DATA_DIR / "return_policy.md")
        )
        intake_agent = create_intake_agent(client, MODEL_NAME)
        policy_agent = create_policy_agent(client, MODEL_NAME, vector_store_id)
        resolution_agent = create_resolution_agent(client, MODEL_NAME)

        # Run pipeline
        intake = run_intake_agent(client, intake_agent, return_request, catalog)
        policy = run_policy_agent(client, policy_agent, intake, catalog)
        resolution = run_resolution_agent(
            client, resolution_agent, intake, policy, return_request, catalog
        )

        # Cleanup
        client.delete_agent(intake_agent.id)
        client.delete_agent(policy_agent.id)
        client.delete_agent(resolution_agent.id)
        client.vector_stores.delete(vector_store_id)

        email = resolution.get("customer_email", {})
        crm = resolution.get("crm_ticket", {})

        return JSONResponse({
            "output": email.get("body", ""),
            "subject": email.get("subject", ""),
            "priority": crm.get("priority", ""),
            "status": crm.get("status", ""),
            "crm_ticket": crm,
            "summary": resolution.get("summary", ""),
        })

    except Exception as e:
        logger.error(f"Pipeline error: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)


if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Returns Resolution Agent server on port 8088")
    uvicorn.run(app, host="0.0.0.0", port=8088)