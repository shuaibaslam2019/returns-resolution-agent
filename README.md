# Returns Resolution Multi-Agent System
### Built on Azure AI Foundry Agent Service

A three-agent pipeline that automates B2B returns management end-to-end:
- **Intake Agent** classifies free-text return requests into structured JSON
- **Policy Agent** checks eligibility via RAG over the return policy document
- **Resolution Agent** drafts a customer email and internal CRM ticket

---

## Architecture

```
Customer Request (free-text)
        │
        ▼
┌─────────────────┐    Code Interpreter
│  Intake Agent   │◄───────────────────
│                 │
│ reason_code     │
│ urgency         │
│ sentiment       │
└────────┬────────┘
         │ structured JSON
         ▼
┌─────────────────┐    File Search (RAG)
│  Policy Agent   │◄──── return_policy.md
│                 │
│ eligible        │
│ refund_type     │
│ priority        │
└────────┬────────┘
         │ eligibility decision
         ▼
┌─────────────────┐
│ Resolution Agent│
│                 │
│ customer email  │
│ CRM ticket JSON │
└─────────────────┘
```

---

## Quick Start

### 1. Local demo (no Azure needed)
```bash
pip install -r requirements.txt
export OPENAI_API_KEY=sk-...

# List all test cases
python demo.py --list

# Run a single case with full output
python demo.py --id RET-2024-001

# Run all 8 cases
python demo.py

# Run without email output (just CRM tickets)
python demo.py --no-email
```

### 2. Azure AI Foundry (production)
```bash
# Set credentials
export AZURE_AI_PROJECT_ENDPOINT=https://<resource>.services.ai.azure.com/api/projects/<project>
export AZURE_MODEL_DEPLOYMENT=gpt-4o

# Login to Azure
az login

# Run all requests
python orchestrator.py

# Run one request with full output
python orchestrator.py --id RET-2024-001 --show-email --show-crm

# Run and delete agents after
python orchestrator.py --cleanup
```

---

## Synthetic Data

The `data/` folder contains realistic B2B logistics scenarios:

| Return ID      | Company                  | Scenario                         |
|----------------|--------------------------|----------------------------------|
| RET-2024-001   | Müller Logistik GmbH     | 4 x DOA barcode scanners         |
| RET-2024-002   | TechDistrib AG           | Wrong model delivered            |
| RET-2024-003   | Österreich Fulfillment   | Cancelled project, unused RFID   |
| RET-2024-004   | Brenntag Logistics       | Conveyor belt damaged in transit |
| RET-2024-005   | FastShip GmbH            | Overstock return, opened boxes   |
| RET-2024-006   | SwissLog Partners        | Safety hazard — forklift shutdown|
| RET-2024-007   | NordPack AG              | Warranty claim — bearing failure |
| RET-2024-008   | Rhenania Distributions   | Overstock, 45 days since order   |

---

## Output Format

Each processed request produces a `output/RET-XXXX-XXX.json` with:
- Full intake classification
- Policy eligibility decision with section references
- Customer-facing email
- CRM ticket payload (compatible with HubSpot / Freshsales / JTL)

---

## Project Structure

```
returns-agent/
├── data/
│   ├── return_requests.json   # 8 synthetic B2B return cases
│   ├── return_policy.md       # Policy document (RAG source)
│   └── product_catalog.json   # Product reference data
├── agents/
│   ├── intake_agent.py        # Agent 1: Classification
│   ├── policy_agent.py        # Agent 2: Eligibility (RAG)
│   └── resolution_agent.py    # Agent 3: Email + CRM
├── orchestrator.py            # Azure Foundry production runner
├── demo.py                    # Local demo runner
├── requirements.txt
└── .env.example
```

---

## Skills Demonstrated

- Multi-agent orchestration with Azure AI Foundry Agent Service
- RAG via File Search on custom policy documents
- Structured output extraction (JSON from free-text LLM responses)
- B2B domain modelling (returns logistics, CRM integration)
- Production patterns: cleanup, error handling, thread management