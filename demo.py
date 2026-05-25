"""
demo.py — Local Demo (No Azure Required)
-----------------------------------------
Simulates the full 3-agent pipeline using GPT-4o via the Anthropic API
so you can demo and test without Azure credentials.

Run: python demo.py
     python demo.py --id RET-2024-001
     python demo.py --list
"""

import json
import argparse
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"


def load_data():
    with open(DATA_DIR / "return_requests.json") as f:
        requests = json.load(f)
    with open(DATA_DIR / "product_catalog.json") as f:
        catalog = json.load(f)
    with open(DATA_DIR / "return_policy.md") as f:
        policy = f.read()
    return requests, catalog, policy


def call_llm(system_prompt: str, user_prompt: str) -> dict:
    """
    Call an LLM to simulate agent behaviour.
    In production this is replaced by the Azure Foundry Agent SDK calls.
    Here we use the openai library as a drop-in for demo purposes.
    """
    try:
        from openai import OpenAI
        client = OpenAI()  # uses OPENAI_API_KEY env var
        response = client.chat.completions.create(
            model="gpt-4o",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
        )
        return json.loads(response.choices[0].message.content)
    except ImportError:
        print("  [demo] openai package not found. Run: pip install openai")
        print("  [demo] Using hardcoded mock response instead.\n")
        return _mock_response()


def _mock_response():
    """Fallback mock when no LLM is available — shows the output shape."""
    return {
        "_note": "This is a mock response. Install 'openai' and set OPENAI_API_KEY for real LLM output.",
        "reason_code": "DEFECTIVE",
        "urgency": "HIGH",
        "eligible": True,
        "refund_type": "REPLACEMENT",
        "priority": "P2",
        "subject": "Your Return Request RET-2024-001 — Replacement Confirmed",
        "body": "Dear Müller Logistik GmbH,\n\nThank you for reporting this issue...",
    }


INTAKE_SYSTEM = """
You are the Intake Agent for a B2B returns management system.
Analyse the customer's return request and produce a structured JSON classification.
Respond with ONLY a valid JSON object.

JSON fields required:
- return_id, company, product_sku, quantity (int)
- reason_code: DEFECTIVE | WRONG_ITEM | TRANSIT_DAMAGE | OVERSTOCK | WARRANTY_CLAIM | SAFETY_HAZARD
- reason_summary (1-2 sentences)
- urgency: HIGH | MEDIUM | LOW
- urgency_justification
- operations_blocked (bool)
- evidence_mentioned (bool)
- days_since_order (int or null)
- sentiment: FRUSTRATED | NEUTRAL | COOPERATIVE
"""

POLICY_SYSTEM = """
You are the Policy Agent for a B2B returns management system.
Evaluate the classified return request against the provided policy document.
Respond with ONLY a valid JSON object.

JSON fields required:
- return_id, eligible (bool), eligibility_reason
- policy_sections_applied (list of strings)
- refund_type: FULL_REFUND | STORE_CREDIT | REPLACEMENT | WARRANTY_REPAIR | PRO_RATA | NOT_ELIGIBLE
- restocking_fee_pct (0 or 15)
- shipping_responsibility: COMPANY | CUSTOMER
- priority: P1 | P2 | P3 | P4
- priority_reason
- requires_inspection (bool), requires_evidence (bool)
- evidence_status: PROVIDED | REQUIRED | NOT_NEEDED
- estimated_resolution_days (int)
- escalation_required (bool)
- escalation_team: TECHNICAL | ACCOUNT_MANAGER | NONE
- notes
"""

RESOLUTION_SYSTEM = """
You are the Resolution Agent for a B2B returns management system.
Generate a professional customer email and internal CRM ticket.
Respond with ONLY a valid JSON object.

JSON fields required:
- return_id
- customer_email: { subject, body (use \\n for line breaks), tone, language }
- crm_ticket: {
    ticket_type, priority, status, assigned_team,
    action_required, sla_days, tags (list), internal_notes,
    refund_amount_eur (int), replacement_required (bool), prepaid_label_required (bool)
  }
- summary (one sentence)
"""


def run_demo_pipeline(request: dict, catalog: dict, policy: str) -> dict:
    """Simulate the full pipeline with direct LLM calls."""

    product = next(
        (p for p in catalog["products"] if p["sku"] == request["product_sku"]),
        {}
    )

    print(f"\n{'─'*60}")
    print(f"  {request['id']} | {request['company']}")
    print('─'*60)

    # ── Stage 1: Intake ────────────────────────────────────────────────────
    print("\n[1/3] Intake Agent — classifying request...")
    intake = call_llm(
        INTAKE_SYSTEM,
        f"""Return ID: {request['id']}
Company: {request['company']}
Product SKU: {request['product_sku']} ({product.get('name', '')})
Unit price: €{product.get('unit_price_eur', '?')}
Customer message: "{request['free_text']}"

Classify this return request."""
    )
    intake["product_sku"] = request["product_sku"]
    print(f"  → Reason: {intake.get('reason_code')} | Urgency: {intake.get('urgency')} | Sentiment: {intake.get('sentiment')}")

    # ── Stage 2: Policy ────────────────────────────────────────────────────
    print("\n[2/3] Policy Agent — checking eligibility...")
    policy_result = call_llm(
        POLICY_SYSTEM,
        f"""Evaluate this return against the policy document.

POLICY DOCUMENT:
{policy}

INTAKE CLASSIFICATION:
{json.dumps(intake, indent=2)}

PRODUCT:
Name: {product.get('name')}
Price: €{product.get('unit_price_eur', 0)}
Warranty: {product.get('warranty_months', 0)} months
High-value (>€5000): {product.get('unit_price_eur', 0) > 5000}

Determine eligibility."""
    )
    eligible_str = "✓ ELIGIBLE" if policy_result.get("eligible") else "✗ NOT ELIGIBLE"
    print(f"  → {eligible_str} | {policy_result.get('refund_type')} | Priority: {policy_result.get('priority')}")

    # ── Stage 3: Resolution ────────────────────────────────────────────────
    print("\n[3/3] Resolution Agent — drafting response...")
    resolution = call_llm(
        RESOLUTION_SYSTEM,
        f"""Generate the customer email and CRM ticket.

ORIGINAL REQUEST:
Company: {request['company']}
Product: {product.get('name', request['product_sku'])}
Customer message: "{request['free_text']}"

INTAKE:
{json.dumps(intake, indent=2)}

POLICY DECISION:
{json.dumps(policy_result, indent=2)}"""
    )
    print(f"  → Email: '{resolution.get('customer_email', {}).get('subject', 'N/A')}'")
    print(f"  → CRM status: {resolution.get('crm_ticket', {}).get('status', 'N/A')}")

    return {
        "return_id": request["id"],
        "company": request["company"],
        "intake": intake,
        "policy": policy_result,
        "resolution": resolution,
    }


def display_result(result: dict, show_email=True, show_crm=True):
    """Display a processed result in readable format."""
    print(f"\n{'='*60}")
    print(f"  RESULT: {result['return_id']} | {result['company']}")
    print('='*60)

    # Policy summary
    p = result.get("policy", {})
    print(f"\n  Eligible:    {p.get('eligible')}")
    print(f"  Refund type: {p.get('refund_type')}")
    print(f"  Priority:    {p.get('priority')}")
    print(f"  Resolution:  ~{p.get('estimated_resolution_days')} days")
    print(f"  Escalation:  {p.get('escalation_team')}")

    if show_email:
        email = result.get("resolution", {}).get("customer_email", {})
        print(f"\n  --- Customer Email ---")
        print(f"  Subject: {email.get('subject', '')}")
        print()
        body = email.get("body", "")
        for line in body.split("\\n"):
            print(f"  {line}")

    if show_crm:
        ticket = result.get("resolution", {}).get("crm_ticket", {})
        print(f"\n  --- CRM Ticket ---")
        for k, v in ticket.items():
            print(f"  {k:30s}: {v}")


def main():
    parser = argparse.ArgumentParser(description="Returns Resolution Agent — Local Demo")
    parser.add_argument("--id", help="Run a single request by ID")
    parser.add_argument("--list", action="store_true", help="List all available return requests")
    parser.add_argument("--no-email", action="store_true", help="Skip printing customer email")
    parser.add_argument("--no-crm", action="store_true", help="Skip printing CRM ticket")
    args = parser.parse_args()

    requests, catalog, policy = load_data()

    if args.list:
        print("\nAvailable return requests:\n")
        for r in requests:
            print(f"  {r['id']:20s} | {r['company']:30s} | {r['product_sku']}")
        return

    if args.id:
        requests = [r for r in requests if r["id"] == args.id]
        if not requests:
            print(f"Return ID '{args.id}' not found. Run with --list to see all IDs.")
            return

    print(f"\nReturns Resolution Multi-Agent Demo")
    print(f"Processing {len(requests)} request(s)...\n")

    results = []
    for request in requests:
        result = run_demo_pipeline(request, catalog, policy)
        results.append(result)

    print(f"\n\n{'='*60}  RESULTS  {'='*60}\n")
    for result in results:
        display_result(result, show_email=not args.no_email, show_crm=not args.no_crm)

    print(f"\n{'─'*60}")
    print("Done. To run on Azure Foundry, use: python orchestrator.py")


if __name__ == "__main__":
    main()