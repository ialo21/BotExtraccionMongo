"""
Lectura del OTP de MongoDB Atlas desde Gmail via Google API.

Busca el correo más reciente de mongodb-account@mongodb.com con el código
de verificación y extrae los 6 dígitos.
"""
import re
import time
import base64
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

import config

_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
_SENDER = "mongodb-account@mongodb.com"
_SUBJECT_RE = re.compile(r"MongoDB verification code", re.IGNORECASE)
_OTP_RE = re.compile(r"\b(\d{6})\b")


def _get_service():
    creds = Credentials.from_authorized_user_file(str(config.GMAIL_TOKEN_PATH), _SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        config.GMAIL_TOKEN_PATH.write_text(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def _extract_otp_from_message(service, msg_id: str) -> str | None:
    msg = service.users().messages().get(
        userId="me", id=msg_id, format="full"
    ).execute()

    headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
    subject = headers.get("Subject", "")
    if not _SUBJECT_RE.search(subject):
        return None

    match = _OTP_RE.search(subject)
    if match:
        return match.group(1)

    parts = msg["payload"].get("parts", [msg["payload"]])
    for part in parts:
        data = part.get("body", {}).get("data", "")
        if data:
            text = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
            match = _OTP_RE.search(text)
            if match:
                return match.group(1)

    return None


def obtener_otp(timeout_seg: int = 60, intervalo_seg: int = 5, after_ts: float | None = None) -> str:
    """
    Espera hasta `timeout_seg` segundos a que llegue el correo de OTP de MongoDB
    y devuelve el código de 6 dígitos.

    Raises:
        TimeoutError: si no llega el correo en el tiempo indicado.
    """
    service = _get_service()
    print(f"  → Esperando OTP en correo (hasta {timeout_seg}s)...")

    # Evita agarrar códigos antiguos: espera mínimo 5s y filtra por timestamp
    time.sleep(5)
    after_clause = f" after:{int(after_ts)}" if after_ts else ""
    deadline = time.time() + timeout_seg
    while time.time() < deadline:
        results = service.users().messages().list(
            userId="me",
            q=(
                f"from:{_SENDER} subject:\"MongoDB verification code\" newer_than:2m"
                f"{after_clause}"
            ),
            maxResults=5,
        ).execute()

        messages = results.get("messages", [])
        for msg in messages:
            # Evita códigos antiguos: revisa timestamp del mensaje
            if after_ts:
                msg_meta = service.users().messages().get(
                    userId="me", id=msg["id"], format="metadata"
                ).execute()
                internal_date_ms = int(msg_meta.get("internalDate", "0"))
                if internal_date_ms < int(after_ts * 1000):
                    continue

            otp = _extract_otp_from_message(service, msg["id"])
            if otp:
                print(f"  → OTP obtenido: {otp}")
                return otp

        # Si no hubo match, espera 5s adicionales y sigue
        time.sleep(max(intervalo_seg, 5))

    raise TimeoutError(
        f"No se recibió el correo de OTP de MongoDB en {timeout_seg} segundos."
    )
