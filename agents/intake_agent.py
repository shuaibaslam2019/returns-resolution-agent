"""
Intake Agent
------------
Takes a raw return request (free-text) + product context,
and outputs a structured classification JSON.

Tools used: Code Interpreter (for structured output validation)
"""

import json
from azure.ai.agents import AgentsClient
from azure.ai.projects.models import CodeInterpreterTool
from azure.identity import DefaultAzureCredential

INTAKE_INSTRUCTIONS = """
You are the Intake Agent for a B2B returns management system.
Your job is to analyse a customer's free-text return request and produce a
structured JSON classification. Be precise and professional.

Always respond with ONLY a valid JSON object — no prose, no markdown fences.

The JSON must have exactly these fields:
{
  "return_id": "<from input>",
  "company": "<from input>",
  "product_sku": "<from input>",
  "quantity": <integer, extract from text or default to 1>,
  "reason_code": "<one of: DEFECTIVE | WRONG_ITEM | TRANSIT_DAMAGE | OVERSTOCK | WARRANTY_CLAIM | SAFETY_HAZARD>",
  "reason_summary": "<1-2 sentence plain English summary of the issue>",
  "urgency": "<HIGH | MEDIUM | LOW>",
  "urgency_justification": "<why this urgency was assigned>",
  "operations_blocked": <true | false>,
  "evidence_mentioned": <true | false>,
  "days_since_order": <integer or null if unknown>,
  "sentiment": "<FRUSTRATED | NEUTRAL | COOPERATIVE>"
}

Urgency rules:
- HIGH: safety hazard OR operations fully blocked OR >1000 units/day throughput mentioned
- MEDIUM: partial impact, wrong item, DOA
- LOW: overstock, no urgency expressed, administrative

Return reason rules:
- DEFECTIVE: item powers on but doesn't work correctly
- WRONG_ITEM: incorrect model/SKU delivered
- TRANSIT_DAMAGE: physical damage from shipping
- OVERSTOCK: no longer needed, excess stock
- WARRANTY_CLAIM: failure within warranty period, component defect
- SAFETY_HAZARD: item poses operational safety risk
"""


def create_intake_agent(client: AgentsClient, model: str) -> object:
    """Create and return the Intake Agent."""
    agent = client.create_agent(
        model=model,
        name="Returns-Intake-Agent",
        instructions=INTAKE_INSTRUCTIONS,
        tools=[CodeInterpreterTool()]
    )
    print(f"[Intake Agent] Created: {agent.id}")
    return agent


def run_intake_agent(
    client: AgentsClient,
    agent,
    return_request: dict,
    product_catalog: dict,
) -> dict:
    """
    Run the intake agent on a single return request.
    Returns structured classification dict.
    """
    thread = client.threads.create()

    # Find product info for context
    product_info = next(
        (p for p in product_catalog["products"] if p["sku"] == return_request["product_sku"]),
        {}
    )

    prompt = f"""
Classify this B2B return request:

RETURN REQUEST:
- Return ID: {return_request['id']}
- Company: {return_request['company']}
- Order ID: {return_request['order_id']}
- Product SKU: {return_request['product_sku']}
- Submitted: {return_request['submitted_at']}
- Customer message: "{return_request['free_text']}"

PRODUCT CONTEXT:
- Product name: {product_info.get('name', 'Unknown')}
- Category: {product_info.get('category', 'Unknown')}
- Unit price: €{product_info.get('unit_price_eur', 'Unknown')}
- Warranty: {product_info.get('warranty_months', 'Unknown')} months

Produce the classification JSON.
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

    # Clean up thread
    client.threads.delete(thread.id)

    # Parse JSON response
    try:
        # Strip any accidental markdown fences
        clean = response_text.strip().strip("```json").strip("```").strip()
        return json.loads(clean)
    except json.JSONDecodeError as e:
        print(f"[Intake Agent] JSON parse error: {e}")
        print(f"[Intake Agent] Raw response: {response_text}")
        return {"error": "parse_failed", "raw": response_text}