import streamlit as st
import requests

# ==========================================
# FastAPI Backend URL Configuration
# ==========================================
API_BASE_URL = "http://127.0.0.1:8000"

st.set_page_config(
    page_title="AI Lead System",
    page_icon="🤖",
    layout="wide"
)

# ==========================================
# Sidebar Navigation Setup
# ==========================================
st.sidebar.title("🤖 AI Lead Manager")
st.sidebar.markdown("---")
page = st.sidebar.radio("Go to:", ["🤖 Client Panel", "🔑 Admin Dashboard"])

# ==========================================
# Session State for Client Chat
# ==========================================
if "active_lead_id" not in st.session_state:
    st.session_state.active_lead_id = None

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if "dev_assigned" not in st.session_state:
    st.session_state.dev_assigned = None

# ==========================================
# Client Panel Page
# ==========================================
if page == "🤖 Client Panel":
    st.title("🤖 Client Capture & Chat Panel")
    st.write("Fills client details, qualifies leads via AI and matches developers instantly.")
    
    st.markdown("### 📝 Capture Form")
    with st.form("client_form"):
        name = st.text_input("Name", placeholder="Enter your name")
        phone = st.text_input("Phone", placeholder="Enter phone number")
        email = st.text_input("Email", placeholder="Enter email address")
        source = st.selectbox(
            "Lead Source",
            ["Website", "Facebook", "Instagram", "LinkedIn", "Google Ads", "WhatsApp", "Referral", "Other"]
        )
        service = st.selectbox(
            "Service Needed",
            ["Website Development", "Application Development", "Backend Development", "UI/UX Design", "Digital Marketing"]
        )
        message = st.text_area("Your Requirement Details", placeholder="Example: I need a business website.")
        
        submitted = st.form_submit_button("🚀 Submit Lead Details")
        
    if submitted:
        if not name or not phone or not email or not message:
            st.error("Please fill all details.")
        else:
            payload = {
                "name": name,
                "phone": phone,
                "email": email,
                "source": source,
                "message": message,
                "interested_service": service
            }
            try:
                response = requests.post(f"{API_BASE_URL}/capture-lead", json=payload)
                if response.status_code == 200:
                    data = response.json()
                    st.session_state.active_lead_id = data["lead_id"]
                    st.success(f"Lead captured successfully! Lead ID: {data['lead_id']} (Status: {data['lead_status']})")
                else:
                    st.error("Failed to capture lead details.")
            except Exception as e:
                st.error("Backend is not running. Please start FastAPI first!")
                
    # Show chat interface if a lead has been successfully captured
    if st.session_state.active_lead_id:
        st.markdown("---")
        st.markdown("### 💬 AI Conversation Assistant")
        
        lead_id = st.session_state.active_lead_id
        
        # Load conversation history from backend
        try:
            res = requests.get(f"{API_BASE_URL}/conversation/{lead_id}")
            if res.status_code == 200:
                convo_data = res.json()
                st.session_state.chat_history = convo_data["conversation"]
                st.session_state.dev_assigned = convo_data["assigned_dev"]
        except Exception:
            pass
            
        # Draw all chat messages
        for chat in st.session_state.chat_history:
            role = "Customer" if chat["role"] == "user" else "AI Assistant"
            st.write(f"**{role}:** {chat['message']}")
            
        # If developer has not been assigned yet, keep chat open
        if not st.session_state.dev_assigned:
            user_input = st.chat_input("Type your reply here...")
            if user_input:
                try:
                    chat_payload = {"lead_id": lead_id, "message": user_input}
                    chat_res = requests.post(f"{API_BASE_URL}/chat", json=chat_payload)
                    if chat_res.status_code == 200:
                        st.rerun()
                except Exception:
                    st.error("Connection error with backend.")
        else:
            st.success(f"Requirement Confirmed! Developer Assigned: **{st.session_state.dev_assigned}**")
            
        if st.button("🔄 Create New Lead"):
            st.session_state.active_lead_id = None
            st.session_state.chat_history = []
            st.session_state.dev_assigned = None
            st.rerun()

# ==========================================
# Admin Dashboard Page
# ==========================================
elif page == "🔑 Admin Dashboard":
    st.title("🔑 Admin Dashboard & CRM")
    st.write("View captured leads, inspect details and browse active developer lists.")
    
    # 1. Fetch leads from backend
    try:
        leads_res = requests.get(f"{API_BASE_URL}/leads")
        devs_res = requests.get(f"{API_BASE_URL}/developers")
        
        if leads_res.status_code == 200 and devs_res.status_code == 200:
            # Parse responses
            leads_data = leads_res.json()
            devs = devs_res.json()
            
            # Convert keys to integer keys to avoid type errors
            leads = {int(l["id"]): l for l in leads_data}
            
            # Simple metrics calculation
            total_leads = len(leads_data)
            hot_leads = sum(1 for l in leads_data if l["lead_status"] == "Hot")
            spam_leads = sum(1 for l in leads_data if l["is_spam"] == 1)
            
            # Display metrics using simple columns
            col1, col2, col3 = st.columns(3)
            col1.metric("Total Leads", total_leads)
            col2.metric("Hot Leads 🔥", hot_leads)
            col3.metric("Spam/Fake Leads ⚠️", spam_leads)
            
            st.markdown("### 📋 Leads List")
            if not leads_data:
                st.info("No leads available.")
            else:
                # Basic Leads table presentation
                st.dataframe(leads_data, use_container_width=True)
                
                st.markdown("---")
                st.markdown("### 🔎 Detailed Lead & Chat Viewer")
                lead_ids = list(leads.keys())
                selected_id = st.selectbox("Select Lead ID to inspect details:", lead_ids)
                
                # Retrieve details of selected lead
                selected_lead = leads[selected_id]
                
                # Show key parameters
                lcol1, lcol2 = st.columns(2)
                lcol1.write(f"**Client Name:** {selected_lead['name']}")
                lcol1.write(f"**Email:** {selected_lead['email']}")
                lcol1.write(f"**Phone:** {selected_lead['phone']}")
                lcol1.write(f"**Service Requested:** {selected_lead['interested_service']}")
                
                lcol2.write(f"**AI Status:** {selected_lead['lead_status']}")
                lcol2.write(f"**Priority:** {selected_lead['follow_up_priority']}")
                lcol2.write(f"**Assigned Dev:** {selected_lead.get('assigned_dev_name')}")
                lcol2.write(f"**AI Summary:** *{selected_lead['ai_summary']}*")
                
                # Load chat logs
                st.markdown("#### Conversation History Log")
                chat_res = requests.get(f"{API_BASE_URL}/conversation/{selected_id}")
                if chat_res.status_code == 200:
                    chat_convo = chat_res.json()["conversation"]
                    if not chat_convo:
                        st.info("No chat logs.")
                    else:
                        for c in chat_convo:
                            actor = "Client" if c["role"] == "user" else "Assistant"
                            st.write(f"**{actor}:** {c['message']}")
            
            st.markdown("---")
            st.markdown("### 👨‍💻 Active Developer Pool")
            st.table(devs)
            
        else:
            st.error("Failed to load data from backend server.")
    except Exception as e:
        st.error(f"FastAPI Backend server connection failed. Error: {str(e)}")