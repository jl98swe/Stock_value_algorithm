"""Manual Gmail SMTP connectivity test. Sends only to the configured sender address."""
import os
import smtplib
import ssl
from email.message import EmailMessage

sender = os.environ["GMAIL_ADDRESS"].strip()
password = os.environ["GMAIL_APP_PASSWORD"].replace(" ", "").strip()
if not sender or not password:
    raise SystemExit("Missing Gmail configuration")

msg = EmailMessage()
msg["From"] = sender
msg["To"] = sender
msg["Subject"] = "Stock Value Alerts – test"
msg.set_content("Detta är ett test av Gmail-utskick från GitHub Actions. Inga prenumeranter har kontaktats.")

with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=30) as smtp:
    smtp.login(sender, password)
    smtp.send_message(msg)
print("SMTP test message submitted to configured sender address.")
