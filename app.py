import os
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ── Config ─────────────────────────────────────────────────────────────────────
API_URL = os.environ.get(
    "API_URL",
    "http://localhost:8088/responses"
)

# ── Page setup ─────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Returns Resolution Agent",
    page_icon="🤖",
    layout="centered"
)

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image("https://avatars.githubusercontent.com/shuaibaslam2019", width=72)
    st.markdown("### Shuaib Aslam")
    st.markdown("Software Developer | LLM & AI Developer |  Azure AI Foundry")
    st.markdown(
        "[GitHub](https://github.com/shuaibaslam2019) · "
        "[LinkedIn](https://linkedin.com/in/m-shuaib-aslam)"
    )
    st.divider()

    st.markdown("**About this project**")
    st.markdown("""
3-agent pipeline on Azure AI Foundry:

🔍 **Intake Agent**
Classifies reason, urgency, sentiment

📋 **Policy Agent**
RAG over return policy document

✉️ **Resolution Agent**
Drafts customer email + CRM ticket
    """)
    st.divider()

    st.markdown("**Stack**")
    st.caption("Azure AI Foundry · Azure Container Apps")
    st.caption("GPT-4.1 · Azure Vector Store")
    st.caption("FastAPI · Docker · Python 3.11")
    st.caption("Sweden Central · OpenTelemetry")
    st.divider()

    st.caption("🔗 [View on GitHub](https://github.com/shuaibaslam2019/returns-resolution-agent)")

# ── Header ─────────────────────────────────────────────────────────────────────
st.title("🤖 Returns Resolution Agent")
st.caption("Built by **Shuaib Aslam** · Powered by Azure AI Foundry Multi-Agent Pipeline")
st.divider()

# ── Session state ──────────────────────────────────────────────────────────────
if "loading" not in st.session_state:
    st.session_state.loading = False
if "result" not in st.session_state:
    st.session_state.result = None
if "last_input" not in st.session_state:
    st.session_state.last_input = ""

# ── Example scenarios ──────────────────────────────────────────────────────────
st.subheader("Try an example scenario")

examples = {
    "🚨 Safety Hazard — Forklift": "Our electric forklift ELT3 has been randomly shutting down mid-operation after only 3 weeks of use. Error code E-14 appears on display. This is a safety hazard — we have paused operations. Need immediate technical support or replacement unit.",
    "📦 Wrong Item Delivered": "We ordered 3 label printers ZT411 but received ZT421 models instead. These are not compatible with our software configuration. We did not order these. Please arrange pickup and send the correct models.",
    "🔧 Warranty Claim": "Our AutoWrap-5 stretch wrap machine purchased 7 months ago has a failed tension roller bearing. Our in-house technician confirmed it is a component defect, not misuse. The machine is under the 12-month warranty.",
    "📉 Overstock Return": "We ordered 20 barcode scanners in August but only need 14. The remaining 6 are unopened in original packaging. We would like store credit if possible.",
    "💥 Transit Damage": "The conveyor belt module M2000 arrived with visible dents on the side panel and one motor mount was cracked. Clearly damaged in transit. We have photos. The unit is not functional.",
}

selected = st.selectbox(
    "Pick a scenario or write your own below:",
    ["Custom"] + list(examples.keys())
)

# ── Input ──────────────────────────────────────────────────────────────────────
st.subheader("Describe your return issue")

default_text = examples[selected] if selected != "Custom" else ""

user_input = st.text_area(
    "Customer message",
    value=default_text,
    height=150,
    placeholder="Describe your return issue in detail — product, problem, urgency...",
    disabled=st.session_state.loading
)

# ── Submit button ──────────────────────────────────────────────────────────────
button_label = "⏳ Processing..." if st.session_state.loading else "🚀 Process Return"

submit = st.button(
    button_label,
    type="primary",
    use_container_width=True,
    disabled=st.session_state.loading
)

# Trigger loading state
if submit and user_input.strip() and not st.session_state.loading:
    st.session_state.loading = True
    st.session_state.last_input = user_input
    st.session_state.result = None
    st.rerun()

elif submit and not user_input.strip():
    st.warning("Please enter a return issue description.")

# ── Pipeline execution ─────────────────────────────────────────────────────────
if st.session_state.loading and st.session_state.last_input:
    with st.spinner("Running 3-agent pipeline... Intake → Policy → Resolution (up to 2 mins)"):
        try:
            response = requests.post(
                API_URL,
                json={"input": st.session_state.last_input},
                timeout=180
            )
            data = response.json()

            if "error" in data:
                st.error(f"Pipeline error: {data['error']}")
                st.session_state.result = None
            else:
                st.session_state.result = data

        except requests.exceptions.Timeout:
            st.error("Request timed out. The pipeline can take up to 3 minutes. Please try again.")
            st.session_state.result = None
        except requests.exceptions.ConnectionError:
            st.error("Could not connect to the API. The service may be starting up — try again in 30 seconds.")
            st.session_state.result = None
        except Exception as e:
            st.error(f"Something went wrong: {str(e)}")
            st.session_state.result = None
        finally:
            st.session_state.loading = False
            st.rerun()

# ── Results ────────────────────────────────────────────────────────────────────
if st.session_state.result:
    data = st.session_state.result

    st.divider()
    st.subheader("✅ Resolution Complete")

    # Summary
    if data.get("summary"):
        st.info(f"**Summary:** {data['summary']}")

    # Priority metric
    priority = data.get("priority", "")
    priority_colors = {"P1": "🔴", "P2": "🟠", "P3": "🟡", "P4": "🟢"}
    icon = priority_colors.get(priority, "⚪")

    col1, col2, col3 = st.columns(3)
    col1.metric("Priority", f"{icon} {priority}")
    col2.metric("Status", data.get("status", ""))
    crm = data.get("crm_ticket", {})
    col3.metric("SLA", f"{crm.get('sla_days', '')} days")

    # Customer email
    st.subheader("📧 Customer Email")
    email = data.get("customer_email", {})

    if isinstance(email, dict):
        subject = email.get("subject", data.get("subject", ""))
        body = email.get("body", data.get("output", ""))
    else:
        subject = data.get("subject", "")
        body = data.get("output", "")

    st.markdown(f"**Subject:** {subject}")
    st.text_area(
        "Email body",
        value=body.replace("\\n", "\n"),
        height=280,
        disabled=True,
        label_visibility="collapsed"
    )

    # CRM ticket
    st.subheader("📋 CRM Ticket")

    if crm:
        col4, col5 = st.columns(2)
        col4.markdown(f"**Ticket type:** {crm.get('ticket_type', '')}")
        col5.markdown(f"**Assigned team:** {crm.get('assigned_team', '')}")

        st.markdown(f"**Action required:** {crm.get('action_required', '')}")

        if crm.get("tags"):
            tags_str = " ".join([f"`{t}`" for t in crm["tags"]])
            st.markdown(f"**Tags:** {tags_str}")

        col6, col7 = st.columns(2)
        col6.markdown(f"**Replacement:** {'✅' if crm.get('replacement_required') else '❌'}")
        col7.markdown(f"**Prepaid label:** {'✅' if crm.get('prepaid_label_required') else '❌'}")

        with st.expander("Internal notes"):
            st.write(crm.get("internal_notes", ""))

        with st.expander("Full CRM payload (JSON)"):
            st.json(crm)

# ── Footer ─────────────────────────────────────────────────────────────────────
st.divider()
st.caption(
    "Built with Azure AI Foundry Agent Service · Azure Container Apps · "
    "GPT-4.1 · FastAPI · Streamlit · "
    "[GitHub](https://github.com/shuaibaslam2019/returns-resolution-agent)"
)