import os
import smtplib
from email.mime.text import MIMEText

from dotenv import load_dotenv

load_dotenv()

SMTP_EMAIL = os.getenv("SMTP_EMAIL")
SMTP_PASSWORD = os.getenv("SMTP_APP_PASSWORD")


def send_verification_email(to_email: str, code: str) -> bool:
    """Envoie le code de verification par email via Gmail SMTP."""
    subject = "Code de verification - Multi-Agent Research Assistant"
    body = f"Votre code de verification est : {code}\n\nCe code expire dans 10 minutes."

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = SMTP_EMAIL
    msg["To"] = to_email

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.sendmail(SMTP_EMAIL, [to_email], msg.as_string())
        return True
    except Exception as e:
        print(f"Erreur envoi email: {e}")
        return False