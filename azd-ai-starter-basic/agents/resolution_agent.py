"""
Resolution Agent
----------------
Takes the intake classification + policy decision and produces:
  1. A professional customer-facing response email
  2. A structured CRM payload (for HubSpot / Freshsales / JTL)

This is the final agent in the pipeline.
"""

import json
from azure.ai.agents import AgentsClient
from azure.identity import DefaultAzureCredential


RESOLUTION_INSTRUCTIONS = """
You are the Resolution Agent for a B2B returns management system.
You write professional, empathetic, and action-oriented responses to B2B customers.

You receive:
- The intake classification (what the customer wants and why)
- The policy decision (whether they're eligible, what they get)

You produce a JSON object with two sections:
1. A customer-facing email response
2. A CRM ticket payload for internal use

Always respond with ONLY a valid JSON object — no prose, no markdown fences.

Email tone guidelines:
- Professional but warm — this is B2B, not robotic corporate speak
- Acknowledge the inconvenience directly for HIGH urgency / P1 / P2 cases
- Be specific: state exactly what happens next and by when
- For ineligible returns, be clear but suggest alternatives (store credit, pro-rata, etc.)
- Sign off as "Returns Management Team, Elvinci"

CRM payload fields should follow standard CRM conventions (ticket type, owner, tags, SLA).

JSON structure:
{
  "return_id": "<from input>",
  "customer_email": {
    "subject": "<email subject line>",
    "body": "<full email body — plain text, use \\n for line breaks>",
    "tone": "<APOLOGETIC | INFORMATIONAL | EMPATHETIC | FIRM>",
    "language": "EN"
  },
  "crm_ticket": {
    "ticket_type": "<WARRANTY | DEFECTIVE | WRONG_ITEM | TRANSIT_DAMAGE | OVERSTOCK | SAFETY>",
    "priority": "<P1 | P2 | P3 | P4>",
    "status": "<OPEN | PENDING_INSPECTION | PENDING_EVIDENCE | APPROVED | REJECTED>",
    "assigned_team": "<TECHNICAL | LOGISTICS | ACCOUNT_MANAGEMENT | STANDARD>",
    "action_required": "<what the internal team must do next>",
    "sla_days": <integer>,
    "tags": ["<relevant tags>"],
    "internal_notes": "<notes for the internal team — not shown to customer>",
    "refund_amount_eur": <estimated amount or 0 if not applicable>,
    "replacement_required": <true | false>,
    "prepaid_label_required": <true | false>
  },
  "summary": "<one-sentence summary of this resolution for logging>"
}
"""


def create_resolution_agent(client: AgentsClient, model: str) -> object:
    """Create and return the Resolution Agent."""
    agent = client.create_agent(
        model=model,
        name="Returns-Resolution-Agent",
        instructions=RESOLUTION_INSTRUCTIONS,
    )
    print(f"[Resolution Agent] Created: {agent.id}")
    return agent


def run_resolution_agent(
    client: AgentsClient,
    agent,
    intake_result: dict,
    policy_result: dict,
    original_request: dict,
    product_catalog: dict,
) -> dict:
    """
    Run the resolution agent to produce email + CRM payload.
    Returns the full resolution dict.
    """
    thread = client.threads.create()

    product_info = next(
        (p for p in product_catalog["products"] if p["sku"] == original_request.get("product_sku", "")),
        {}
    )

    prompt = f"""
Generate the customer response email and CRM ticket for this return case.

ORIGINAL REQUEST:
- Company: {original_request['company']}
- Product: {product_info.get('name', original_request['product_sku'])}
- Customer message: "{original_request['free_text']}"

INTAKE CLASSIFICATION:
{json.dumps(intake_result, indent=2)}

POLICY DECISION:
{json.dumps(policy_result, indent=2)}

Generate the full resolution JSON including the customer email and CRM ticket.
"""

    client.messages.create(
        thread_id=thread.id,
        role="user",
        content=prompt,
    )

    run = client.runs.create_and_process(
        thread_id=thread.id,
        agent_id=agent.id,
    )

    messages = client.messages.list(thread_id=thread.id)
    response_text = ""
    for msg in messages:
        if msg.role == "assistant":
            for block in msg.content:
                if hasattr(block, "text"):
                    response_text = block.text.value
                    break
            break

    client.threads.delete(thread.id)

    try:
        clean = response_text.strip().strip("```json").strip("```").strip()
        return json.loads(clean)
    except json.JSONDecodeError as e:
        print(f"[Resolution Agent] JSON parse error: {e}")
        return {"error": "parse_failed", "raw": response_text}