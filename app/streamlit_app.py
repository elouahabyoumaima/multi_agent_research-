import os

import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")
ACCENT = "#10a37f"

st.set_page_config(page_title="Research Assistant", page_icon="", layout="centered")

st.markdown(f"""
<style>
    .stApp {{ background-color: #FFFFFF; }}
    #MainMenu, footer {{ visibility: hidden; }}

    .main-header {{ text-align: center; padding: 1.2rem 0 1.5rem 0; }}
    .main-header h1 {{ color: #111111; font-size: 1.6rem; font-weight: 600; margin-bottom: 0.2rem; }}
    .main-header p {{ color: #6B7280; font-size: 0.9rem; }}

    .step-badge {{
        display: inline-block;
        background-color: {ACCENT}1A;
        color: {ACCENT};
        padding: 3px 12px;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 600;
        margin: 2px 4px 2px 0;
    }}

    section[data-testid="stSidebar"] {{
        background-color: #F7F7F8;
        border-right: 1px solid #E5E7EB;
    }}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="main-header">
    <h1>🔎 Multi-Agent Research Assistant</h1>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("###  Exemples")
    st.markdown(
        "- Quels sont les avantages de Rust par rapport à Go ?\n"
        "- Quel est le meilleur framework backend en 2026 ?\n"
        "- Comment fonctionne le protocole MCP ?"
    )

question = st.text_area("Pose ta question de recherche :", height=80, placeholder="Ex: Quels sont les avantages de Rust par rapport à Go ?")

if st.button("🔎 Lancer la recherche", use_container_width=True, type="primary"):
    if not question.strip():
        st.warning("Écris une question d'abord.")
    else:
        with st.spinner("Planification, recherche et rédaction en cours (1-2 minutes)..."):
            try:
                response = requests.post(f"{API_URL}/research", json={"question": question}, timeout=180)
                response.raise_for_status()
                result = response.json()
            except Exception as e:
                st.error(f"Erreur : {e}")
                result = None

        if result:
            st.caption(f"⏱️ Terminé en {result['duration_seconds']}s")
            for sq in result["sub_questions"]:
                st.markdown(f'<span class="step-badge">{sq[:60]}...</span>', unsafe_allow_html=True)

            st.markdown("---")
            st.markdown(result["report"])