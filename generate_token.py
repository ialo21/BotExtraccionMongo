"""
Script one-shot para generar token.json con acceso Gmail (solo correr una vez).

Uso:
    python generate_token.py

Abrirá el navegador para autorizar la cuenta de Gmail que recibe el OTP.
El token resultante se guarda en la ruta configurada en GMAIL_TOKEN_PATH (.env).
"""
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from dotenv import load_dotenv
import os

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
CREDS_PATH = Path(os.getenv("GMAIL_CREDS_PATH", "AuthParaScriptingIago.json"))
TOKEN_PATH = Path(os.getenv("GMAIL_TOKEN_PATH", "token.json"))

if TOKEN_PATH.exists():
    print(f"[INFO] Ya existe {TOKEN_PATH}. Elimínalo si quieres regenerarlo.")
    raise SystemExit(0)

if not CREDS_PATH.exists():
    raise FileNotFoundError(f"No se encontró el archivo de credenciales: {CREDS_PATH}")

flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_PATH), SCOPES)
creds = flow.run_local_server(port=0)

TOKEN_PATH.write_text(creds.to_json())
print(f"[OK] Token guardado en {TOKEN_PATH}")
