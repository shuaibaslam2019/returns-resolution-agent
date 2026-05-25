"""
Policy Agent
------------
Takes the structured classification from the Intake Agent and
checks it against the return policy document (RAG via File Search).

Returns an eligibility decision with reasoning and applicable policy sections.
"""

import json
import os
from azure.ai.agents import AgentsClient
from azure.ai.agents.models import FileSearchTool
from azure.identity import DefaultAzureCredential
from azure.ai.agents.models import FilePurpose
from azure.ai.agents.models import FileSearchToolDefinition, ToolResources, FileSearchToolResource


POLICY_INSTRUCTIONS = """
You are the Policy Agent for a B2B returns management system.
You have access to the official Return & Refund Policy document via file search.

Your job is to evaluate a classified return request against the policy and
determine eligibility, refund type, priority level, and required next steps.

Always respond with ONLY a valid JSON object — no prose, no markdown fences.

The JSON must have exactly these fields:
{
  "return_id": "<from input>",
  "eligible": <true | false>,
  "eligibility_reason": "<clear explanation referencing the policy>",
  "policy_sections_applied": ["<list of policy section numbers or names used>"],
  "refund_type": "<FULL_REFUND | STORE_CREDIT | REPLACEMENT | WARRANTY_REPAIR | PRO_RATA | NOT_ELIGIBLE>",
  "restocking_fee_pct": <0 or 15>,
  "shipping_responsibility": "<COMPANY | CUSTOMER>",
  "priority": "<P1 | P2 | P3 | P4>",
  "priority_reason": "<why this priority was assigned>",
  "requires_inspection": <true | false>,
  "requires_evidence": <true | false>,
  "evidence_status": "<PROVIDED | REQUIRED | NOT_NEEDED>",
  "estimated_resolution_days": <integer>,
  "escalation_required": <true | false>,
  "escalation_team": "<TECHNICAL | ACCOUNT_MANAGER | NONE>",
  "notes": "<any additional policy guidance or edge cases>"
}
"""


def upload_policy_document(client: AgentsClient, policy_path: str) -> str:
    """Upload the policy document and create a vector store for RAG."""
    print("[Policy Agent] Uploading policy document to vector store...")

    
    file = client.files.upload_and_poll(
        file_path=policy_path,
        purpose=FilePurpose.AGENTS,
    )

    vector_store = client.vector_stores.create_and_poll(
        name="ReturnsPolicyVectorStore",
        file_ids=[file.id],
    )

    print(f"[Policy Agent] Vector store ready: {vector_store.id}")
    return vector_store.id


def create_policy_agent(client, model: str, vector_store_id: str):
    agent = client.create_agent(
        model=model,
        name="Returns-Policy-Agent",
        instructions=POLICY_INSTRUCTIONS,
        tools=[FileSearchToolDefinition()],
        tool_resources=ToolResources(
            file_search=FileSearchToolResource(
                vector_store_ids=[vector_store_id]
            )
        ),
    )
    print(f"[Policy Agent] Created: {agent.id}")
    return agent


def run_policy_agent(
    client: AgentsClient,
    agent,
    intake_result: dict,
    product_catalog: dict,
) -> dict:
    """
    Run the policy agent on an intake classification.
    Returns eligibility decision dict.
    """
    thread = client.threads.create()

    product_info = next(
        (p for p in product_catalog["products"] if p["sku"] == intake_result.get("product_sku", "")),
        {}
    )

    prompt = f"""
Evaluate this classified return request against the return policy document.

INTAKE CLASSIFICATION:
{json.dumps(intake_result, indent=2)}

PRODUCT DETAILS:
- Product name: {product_info.get('name', 'Unknown')}
- Unit price: €{product_info.get('unit_price_eur', 0)}
- Warranty: {product_info.get('warranty_months', 0)} months
- High-value item (>€5000): {product_info.get('unit_price_eur', 0) > 5000}

Search the policy document and determine:
1. Is this return eligible?
2. What refund type applies?
3. What priority should be assigned?
4. What are the required next steps?

Produce the eligibility decision JSON.
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
        print(f"[Policy Agent] JSON parse error: {e}")
        return {"error": "parse_failed", "raw": response_text}