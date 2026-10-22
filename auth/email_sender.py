import os
import smtplib
from email.mime.text import MIMEText

import requests
from dotenv import load_dotenv

load_dotenv()

# --- Cloud (Streamlit Cloud, Render...) : le SMTP est souvent bloque -> API HTTPS de Brevo ---
BREVO_API_KEY = os.getenv("BREVO_API_KEY")
BREVO_SENDER_EMAIL = os.getenv("BREVO_SENDER_EMAIL") or os.getenv("SMTP_EMAIL")
BREVO_SENDER_NAME = os.getenv("BREVO_SENDER_NAME", "Multi-Agent Research Assistant")

# --- Local : Gmail SMTP (comme avant) ---
SMTP_EMAIL = os.getenv("SMTP_EMAIL")
SMTP_PASSWORD = os.getenv("SMTP_APP_PASSWORD")

SUBJECT = "Code de verification - Multi-Agent Research Assistant"


def _body(code: str) -> str:
    return (
        "Bonjour,\n\n"
        f"Ton code de verification est : {code}\n\n"
        "Ce code expire dans 10 minutes.\n"
        "Si tu n'es pas a l'origine de cette inscription, ignore ce message.\n"
    )


def _send_brevo(to_email: str, code: str) -> bool:
    """Envoie l'email via l'API HTTPS de Brevo (port 443, jamais bloque)."""
    try:
        resp = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"api-key": BREVO_API_KEY, "accept": "application/json", "content-type": "application/json"},
            json={
                "sender": {"name": BREVO_SENDER_NAME, "email": BREVO_SENDER_EMAIL},
                "to": [{"email": to_email}],
                "subject": SUBJECT,
                "textContent": _body(code),
            },
            timeout=20,
        )
        if resp.status_code in (200, 201, 202):
            return True
        print("Brevo: echec", resp.status_code, resp.text[:300])
        return False
    except Exception as e:
        print("Brevo: erreur", e)
        return False


def _send_smtp(to_email: str, code: str) -> bool:
    """Envoie le code de verification par email via Gmail SMTP."""
    msg = MIMEText(_body(code), "plain", "utf-8")
    msg["Subject"] = SUBJECT
    msg["From"] = SMTP_EMAIL
    msg["To"] = to_email
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as server:
            server.starttls()
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.sendmail(SMTP_EMAIL, [to_email], msg.as_string())
        return True
    except Exception as e:
        print("SMTP: erreur", e)
        return False


def send_verification_email(to_email: str, code: str) -> bool:
    """Brevo si BREVO_API_KEY est defini (cloud), sinon Gmail SMTP (local)."""
    if BREVO_API_KEY and BREVO_SENDER_EMAIL:
        return _send_brevo(to_email, code)
    return _send_smtp(to_email, code)