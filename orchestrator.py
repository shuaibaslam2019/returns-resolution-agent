"""
orchestrator.py
---------------
Main pipeline that wires all three agents together.
Runs a return request through:
  Intake Agent → Policy Agent → Resolution Agent

Usage:
  python orchestrator.py                    # runs all requests in data/
  python orchestrator.py --id RET-2024-001  # runs a single request
  python orchestrator.py --cleanup          # deletes all created agents
"""
from dotenv import load_dotenv
load_dotenv()


import os
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry import trace
from azure.ai.agents.telemetry import AIAgentsInstrumentor

configure_azure_monitor(
    connection_string=os.environ["APPLICATIONINSIGHTS_CONNECTION_STRING"]
)

# Enable agent instrumentation
AIAgentsInstrumentor().instrument(enable_content_recording=True)

import json
import argparse
from pathlib import Path
from datetime import datetime, timezone
from azure.ai.agents import AgentsClient
from azure.identity import DefaultAzureCredential
from azure.identity.broker import InteractiveBrowserBrokerCredential
from azure.identity import AzureCliCredential

from agents.intake_agent import create_intake_agent, run_intake_agent
from agents.policy_agent import create_policy_agent, upload_policy_document, run_policy_agent
from agents.resolution_agent import create_resolution_agent, run_resolution_agent


# ── Config ─────────────────────────────────────────────────────────────────
PROJECT_ENDPOINT = os.environ.get("AZURE_AI_PROJECT_ENDPOINT", "")
MODEL_NAME = os.environ.get("AZURE_MODEL_DEPLOYMENT", "gpt-4o")

DATA_DIR = Path(__file__).parent / "data"
OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


def load_data():
    with open(DATA_DIR / "return_requests.json") as f:
        requests = json.load(f)
    with open(DATA_DIR / "product_catalog.json") as f:
        catalog = json.load(f)
    return requests, catalog


def print_separator(label: str):
    print(f"\n{'─' * 60}")
    print(f"  {label}")
    print('─' * 60)


def run_pipeline(request: dict, catalog: dict, agents: dict) -> dict:
    """Run a single return request through the full 3-agent pipeline."""
    client = agents["client"]

    print_separator(f"Processing: {request['id']} | {request['company']}")

    # ── Stage 1: Intake ────────────────────────────────────────────────────
    print("\n[1/3] Running Intake Agent...")
    intake_result = run_intake_agent(client, agents["intake"], request, catalog)

    if "error" in intake_result:
        print(f"  ✗ Intake Agent failed: {intake_result}")
        return {"return_id": request["id"], "status": "failed", "stage": "intake"}

    print(f"  ✓ Reason: {intake_result.get('reason_code')} | "
          f"Urgency: {intake_result.get('urgency')} | "
          f"Sentiment: {intake_result.get('sentiment')}")

    # ── Stage 2: Policy ────────────────────────────────────────────────────
    print("\n[2/3] Running Policy Agent...")
    policy_result = run_policy_agent(client, agents["policy"], intake_result, catalog)

    if "error" in policy_result:
        print(f"  ✗ Policy Agent failed: {policy_result}")
        return {"return_id": request["id"], "status": "failed", "stage": "policy"}

    eligible_str = "✓ ELIGIBLE" if policy_result.get("eligible") else "✗ NOT ELIGIBLE"
    print(f"  {eligible_str} | "
          f"Type: {policy_result.get('refund_type')} | "
          f"Priority: {policy_result.get('priority')}")

    # ── Stage 3: Resolution ────────────────────────────────────────────────
    print("\n[3/3] Running Resolution Agent...")
    resolution_result = run_resolution_agent(
        client, agents["resolution"], intake_result, policy_result, request, catalog
    )

    if "error" in resolution_result:
        print(f"  ✗ Resolution Agent failed: {resolution_result}")
        return {"return_id": request["id"], "status": "failed", "stage": "resolution"}

    email_subject = resolution_result.get("customer_email", {}).get("subject", "N/A")
    crm_status = resolution_result.get("crm_ticket", {}).get("status", "N/A")
    print(f"  ✓ Email ready: '{email_subject}'")
    print(f"  ✓ CRM ticket status: {crm_status}")

    # ── Combine full result ────────────────────────────────────────────────
    full_result = {
        "return_id": request["id"],
        "company": request["company"],
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "status": "completed",
        "intake": intake_result,
        "policy": policy_result,
        "resolution": resolution_result,
    }

    # Save to output file
    out_path = OUTPUT_DIR / f"{request['id']}.json"
    with open(out_path, "w") as f:
        json.dump(full_result, f, indent=2)
    print(f"\n  → Saved to {out_path}")

    return full_result


def print_customer_email(result: dict):
    """Pretty-print the customer email from a result."""
    email = result.get("resolution", {}).get("customer_email", {})
    if not email:
        return
    print_separator(f"Customer Email — {result['return_id']}")
    print(f"Subject: {email.get('subject', '')}\n")
    print(email.get("body", ""))


def print_crm_ticket(result: dict):
    """Pretty-print the CRM ticket from a result."""
    ticket = result.get("resolution", {}).get("crm_ticket", {})
    if not ticket:
        return
    print_separator(f"CRM Ticket — {result['return_id']}")
    for k, v in ticket.items():
        print(f"  {k:30s}: {v}")


def setup_agents(client):
    """Create all three agents and upload policy document."""
    print("\n[Setup] Creating agents...")

    vector_store_id = upload_policy_document(
        client, str(DATA_DIR / "return_policy.md")
    )

    return {
        "client": client,
        "intake": create_intake_agent(client, MODEL_NAME),
        "policy": create_policy_agent(client, MODEL_NAME, vector_store_id),
        "resolution": create_resolution_agent(client, MODEL_NAME),
        "vector_store_id": vector_store_id,
    }


def cleanup_agents(client, agents: dict):
    """Delete all created agents and vector stores."""
    print("\n[Cleanup] Deleting agents...")
    for key in ["intake", "policy", "resolution"]:
        if key in agents:
            client.delete_agent(agents[key].id)
            print(f"  Deleted: {key} agent ({agents[key].id})")
    if "vector_store_id" in agents:
        client.vector_stores.delete(agents["vector_store_id"])
        print(f"  Deleted vector store: {agents['vector_store_id']}")


def main():
    parser = argparse.ArgumentParser(description="Returns Resolution Multi-Agent Pipeline")
    parser.add_argument("--id", help="Process a single return request by ID")
    parser.add_argument("--show-email", action="store_true", help="Print customer email after processing")
    parser.add_argument("--show-crm", action="store_true", help="Print CRM ticket after processing")
    parser.add_argument("--cleanup", action="store_true", help="Delete agents after run")
    args = parser.parse_args()

    if not PROJECT_ENDPOINT:
        print("ERROR: Set AZURE_AI_PROJECT_ENDPOINT environment variable.")
        print("  export AZURE_AI_PROJECT_ENDPOINT=https://<resource>.services.ai.azure.com/api/projects/<project>")
        return

    client = AgentsClient(
        endpoint=PROJECT_ENDPOINT,
        credential=AzureCliCredential(),
    )

    requests, catalog = load_data()

    if args.id:
        requests = [r for r in requests if r["id"] == args.id]
        if not requests:
            print(f"Return ID '{args.id}' not found.")
            return

    agents = setup_agents(client)
    results = []

    try:
        for request in requests:
            result = run_pipeline(request, catalog, agents)
            results.append(result)
    finally:
        cleanup_agents(client, agents)  # always runs, even on error

    # Summary
    print_separator("Run Summary")
    for r in results:
        status_icon = "✓" if r["status"] == "completed" else "✗"
        eligible = r.get("policy", {}).get("eligible", "?")
        priority = r.get("policy", {}).get("priority", "?")
        refund = r.get("policy", {}).get("refund_type", "?")
        print(f"  {status_icon} {r['return_id']:20s} | eligible={eligible} | {priority} | {refund}")

    print(f"\nOutputs saved to: {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()