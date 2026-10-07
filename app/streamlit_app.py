import io
import os

import textwrap
import requests
import streamlit as st
from docx import Document
from fpdf import FPDF

API_URL = os.getenv("API_URL", "http://localhost:8000")
ACCENT = "#10a37f"

st.set_page_config(page_title="Research Assistant", page_icon="🔎", layout="centered")

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

# ---------------------------------------------------------------------------
# Etat de session
# ---------------------------------------------------------------------------
if "token" not in st.session_state:
    st.session_state.token = None
if "username" not in st.session_state:
    st.session_state.username = None


def auth_headers():
    return {"Authorization": "Bearer " + st.session_state.token}


# ---------------------------------------------------------------------------
# Export du rapport
# ---------------------------------------------------------------------------
import textwrap

def clean_markdown_for_pdf(text):
    # remplace les caracteres unicode courants par leur equivalent ASCII
    # (evite le `?` que latin-1 mettrait a la place)
    replacements = {
        "\u2019": "'", "\u2018": "'",
        "\u201c": '"', "\u201d": '"',
        "\u2013": "-", "\u2014": "-",
        "\u2026": "...",
        "\u00a0": " ",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    lines = []
    for line in text.split("\n"):
        stripped = line.strip()

        # separateurs de tableau markdown "|---|---|" -> on saute
        if stripped.replace("|", "").replace("-", "").replace(":", "").strip() == "" and "|" in stripped:
            continue

        # titres "# ", "## ", "### " -> on garde le texte, en majuscules
        if stripped.startswith("#"):
            clean = stripped.lstrip("#").strip()
            lines.append("")
            lines.append(clean.upper())
            lines.append("")
            continue

        # gras/italique markdown -> on enleve juste les symboles
        clean = stripped.replace("**", "").replace("*", "")
        # separateur horizontal "---"
        if clean == "---":
            lines.append("-" * 50)
            continue

        lines.append(clean)

    return "\n".join(lines)


def report_to_pdf(report_text):
    cleaned_text = clean_markdown_for_pdf(report_text)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)

    usable_width = pdf.w - pdf.l_margin - pdf.r_margin

    for line in cleaned_text.split("\n"):
        safe_line = line.encode("latin-1", "replace").decode("latin-1")

        if not safe_line.strip():
            pdf.ln(4)
            continue

        wrapped_lines = textwrap.wrap(safe_line, width=90, break_long_words=True, break_on_hyphens=True) or [""]
        for wrapped_line in wrapped_lines:
            pdf.set_x(pdf.l_margin)
            try:
                pdf.multi_cell(usable_width, 6, wrapped_line)
            except Exception:
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(usable_width, 6, "[ligne non affichable]")

    return bytes(pdf.output())

def report_to_docx(report_text):
    doc = Document()
    for line in report_text.split("\n"):
        doc.add_paragraph(line)
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def render_export_buttons(report_text, key_prefix):
    col1, col2, col3 = st.columns(3)
    with col1:
        st.download_button(
            "📄 TXT",
            report_text,
            file_name="rapport.txt",
            key=key_prefix + "_txt",
            use_container_width=True,
        )
    with col2:
        st.download_button(
            "📕 PDF",
            report_to_pdf(report_text),
            file_name="rapport.pdf",
            mime="application/pdf",
            key=key_prefix + "_pdf",
            use_container_width=True,
        )
    with col3:
        docx_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        st.download_button(
            "📘 Word",
            report_to_docx(report_text),
            file_name="rapport.docx",
            mime=docx_mime,
            key=key_prefix + "_docx",
            use_container_width=True,
        )


# ---------------------------------------------------------------------------
# Page de connexion / inscription
# ---------------------------------------------------------------------------
def login_page():
    header_html = (
        '<div class="main-header">'
        '<h1>Multi-Agent Research Assistant</h1>'
        '<p>Connecte-toi pour acceder a l assistant et ton historique</p>'
        '</div>'
    )
    st.markdown(header_html, unsafe_allow_html=True)

    tab_login, tab_signup = st.tabs(["Connexion", "Creer un compte"])

    with tab_login:
        with st.form("login_form"):
            username = st.text_input("Nom d'utilisateur", key="login_username")
            password = st.text_input("Mot de passe", type="password", key="login_password")
            submitted = st.form_submit_button("Se connecter", use_container_width=True, type="primary")
            if submitted:
                try:
                    url = API_URL + "/auth/login"
                    payload = {"username": username, "password": password}
                    resp = requests.post(url, json=payload)
                    if resp.status_code == 200:
                        st.session_state.token = resp.json()["access_token"]
                        st.session_state.username = username
                        st.rerun()
                    else:
                        st.error(resp.json().get("detail", "Erreur de connexion"))
                except Exception as e:
                    st.error("Erreur : " + str(e))

    with tab_signup:
        with st.form("signup_form"):
            username = st.text_input("Nom d'utilisateur", key="signup_username")
            password = st.text_input("Mot de passe", type="password", key="signup_password")
            submitted = st.form_submit_button("Creer le compte", use_container_width=True, type="primary")
            if submitted:
                try:
                    url = API_URL + "/auth/signup"
                    payload = {"username": username, "password": password}
                    resp = requests.post(url, json=payload)
                    if resp.status_code == 200:
                        st.session_state.token = resp.json()["access_token"]
                        st.session_state.username = username
                        st.rerun()
                    else:
                        st.error(resp.json().get("detail", "Erreur lors de la creation"))
                except Exception as e:
                    st.error("Erreur : " + str(e))


# ---------------------------------------------------------------------------
# Page principale (apres connexion)
# ---------------------------------------------------------------------------
def main_page():
    header_html = (
        '<div class="main-header">'
        '<h1>Multi-Agent Research Assistant</h1>'
        '<p>Planification -> Recherche (web + MCP) -> Synthese</p>'
        '</div>'
    )
    st.markdown(header_html, unsafe_allow_html=True)

    with st.sidebar:
        st.markdown("### Utilisateur : " + st.session_state.username)
        if st.button("Se deconnecter", use_container_width=True):
            st.session_state.token = None
            st.session_state.username = None
            st.rerun()

        st.markdown("---")
        st.markdown("### Historique")
        try:
            resp = requests.get(API_URL + "/history", headers=auth_headers())
            history = resp.json() if resp.status_code == 200 else []
        except Exception:
            history = []

        if not history:
            st.caption("Aucune recherche pour l'instant.")
        else:
            for item in history:
                label = item["question"][:40]
                if len(item["question"]) > 40:
                    label = label + "..."
                if st.button(label, key="hist_" + str(item["id"]), use_container_width=True):
                    st.session_state.viewing = item
                    st.rerun()

    # affichage d'un element d'historique selectionne
    if st.session_state.get("viewing"):
        item = st.session_state.viewing
        caption_text = "Recherche du " + item["created_at"][:10] + " -- " + str(item["duration_seconds"]) + "s"
        st.caption(caption_text)
        if st.button("Retour / Nouvelle recherche"):
            st.session_state.viewing = None
            st.rerun()
        st.markdown("---")
        st.markdown(item["report"])
        render_export_buttons(item["report"], "hist_" + str(item["id"]))
        return

    question = st.text_area(
        "Pose ta question de recherche :",
        height=80,
        placeholder="Ex: Quels sont les avantages de Rust par rapport a Go ?",
    )

    if st.button("Lancer la recherche", use_container_width=True, type="primary"):
        if not question.strip():
            st.warning("Ecris une question d'abord.")
        else:
            with st.spinner("Planification, recherche et redaction en cours (1-2 minutes)..."):
                try:
                    url = API_URL + "/research"
                    payload = {"question": question}
                    headers = auth_headers()
                    resp = requests.post(url, json=payload, headers=headers, timeout=180)
                    resp.raise_for_status()
                    result = resp.json()
                except Exception as e:
                    st.error("Erreur : " + str(e))
                    result = None

            if result:
                st.session_state.last_result = result

    if st.session_state.get("last_result") and not st.session_state.get("viewing"):
        result = st.session_state.last_result
        st.caption("Termine en " + str(result["duration_seconds"]) + "s")
        for sq in result["sub_questions"]:
            badge_html = '<span class="step-badge">' + sq[:60] + "...</span>"
            st.markdown(badge_html, unsafe_allow_html=True)
        st.markdown("---")
        st.markdown(result["report"])
        render_export_buttons(result["report"], "last")


# ---------------------------------------------------------------------------
# Routage
# ---------------------------------------------------------------------------
if st.session_state.token is None:
    login_page()
else:
    main_page()