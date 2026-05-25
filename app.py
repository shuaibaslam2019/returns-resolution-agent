import streamlit as st
import requests
import json

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Returns Resolution Agent",
    page_icon="🤖",
    layout="centered"
)

# ── API endpoint ───────────────────────────────────────────────────────────────
API_URL = "https://returns-agent-app--v3.kindsky-528b62e5.swedencentral.azurecontainerapps.io/responses"

# ── Header ─────────────────────────────────────────────────────────────────────
st.title("🤖 Returns Resolution Agent")
st.caption("Powered by Azure AI Foundry — Multi-Agent Pipeline")
st.divider()

# ── Example cases ──────────────────────────────────────────────────────────────
st.subheader("Try an example")
examples = {
    "🚨 Safety Hazard — Forklift": "Our electric forklift ELT3 has been randomly shutting down mid-operation after only 3 weeks of use. Error code E-14 appears on display. This is a safety hazard — we have paused operations.",
    "📦 Wrong Item Delivered": "We ordered 3 label printers ZT411 but received ZT421 models instead. These are not compatible with our software. Please arrange pickup and send the correct models.",
    "🔧 Warranty Claim": "Our AutoWrap-5 stretch wrap machine purchased 7 months ago has a failed tension roller bearing. Our technician confirmed it is a component defect. The machine is under 12-month warranty.",
    "📉 Overstock Return": "We ordered 20 barcode scanners in August but only need 14. The remaining 6 are unopened in original packaging. We would like store credit.",
    "💥 Transit Damage": "The conveyor belt module M2000 arrived with visible dents and a cracked motor mount. Clearly damaged in transit. We have photos. The unit is not functional.",
}

selected = st.selectbox("Pick a scenario or write your own below:", ["Custom"] + list(examples.keys()))

# ── Input ──────────────────────────────────────────────────────────────────────
st.subheader("Describe your return issue")

if selected != "Custom":
    default_text = examples[selected]
else:
    default_text = ""

user_input = st.text_area(
    "Customer message",
    value=default_text,
    height=150,
    placeholder="Describe your return issue in detail..."
)

submit = st.button("🚀 Process Return", type="primary", use_container_width=True)

# ── Process ────────────────────────────────────────────────────────────────────
if submit and user_input.strip():
    with st.spinner("Running 3-agent pipeline... (Intake → Policy → Resolution)"):
        try:
            response = requests.post(
                API_URL,
                json={"input": user_input},
                timeout=120
            )
            data = response.json()

            if "error" in data:
                st.error(f"Error: {data['error']}")
            else:
                # ── Results ────────────────────────────────────────────────────
                st.divider()
                st.subheader("✅ Resolution Complete")

                # Summary
                if data.get("summary"):
                    st.info(f"**Summary:** {data['summary']}")

                # Priority badge
                priority = data.get("priority", "")
                priority_colors = {
                    "P1": "🔴", "P2": "🟠", "P3": "🟡", "P4": "🟢"
                }
                icon = priority_colors.get(priority, "⚪")
                st.metric("Priority", f"{icon} {priority}")

                # Email
                st.subheader("📧 Customer Email")
                email = data.get("customer_email", {})
                if isinstance(email, dict):
                    subject = email.get("subject", data.get("subject", ""))
                    body = email.get("body", data.get("output", ""))
                else:
                    subject = data.get("subject", "")
                    body = data.get("output", "")

                st.markdown(f"**Subject:** {subject}")
                st.text_area("Email body", value=body.replace("\\n", "\n"), height=300, disabled=True)

                # CRM Ticket
                st.subheader("📋 CRM Ticket")
                crm = data.get("crm_ticket", {})
                if crm:
                    col1, col2, col3 = st.columns(3)
                    col1.markdown(f"**Type**\n\n{crm.get('ticket_type', '')}")
                    col2.markdown(f"**Status**\n\n{crm.get('status', '')}")
                    col3.markdown(f"**SLA**\n\n{crm.get('sla_days', '')} days")

                    st.markdown(f"**Assigned Team:** {crm.get('assigned_team', '')}")
                    st.markdown(f"**Action Required:** {crm.get('action_required', '')}")

                    if crm.get("tags"):
                        tags_str = " ".join([f"`{t}`" for t in crm["tags"]])
                        st.markdown(f"**Tags:** {tags_str}")

                    col4, col5 = st.columns(2)
                    col4.markdown(f"**Replacement Required:** {'✅' if crm.get('replacement_required') else '❌'}")
                    col5.markdown(f"**Prepaid Label:** {'✅' if crm.get('prepaid_label_required') else '❌'}")

                    with st.expander("Internal Notes"):
                        st.write(crm.get("internal_notes", ""))

        except requests.exceptions.Timeout:
            st.error("Request timed out — the pipeline can take up to 2 minutes. Please try again.")
        except Exception as e:
            st.error(f"Something went wrong: {str(e)}")

elif submit and not user_input.strip():
    st.warning("Please enter a return issue description.")

# ── Footer ─────────────────────────────────────────────────────────────────────
st.divider()
st.caption("Built with Azure AI Foundry Agent Service · Azure Container Apps · Streamlit")