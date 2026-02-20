from pathlib import Path
from dotenv import load_dotenv
import json
import os

load_dotenv()

# ── Credenciales ──────────────────────────────────────────────────────────────
MONGO_ATLAS_URL: str = os.getenv("MONGO_ATLAS_URL", "https://cloud.mongodb.com")
MONGO_USER: str = os.getenv("MONGO_USER", "")
MONGO_PASSWORD: str = os.getenv("MONGO_PASSWORD", "")

# ── Rutas ─────────────────────────────────────────────────────────────────────
# Si el orquestador inyecta EJECUCION_RESULTADOS_DIR, todo va ahí.
# Si no, se usan las rutas locales del .env o los defaults.
_resultados_dir = os.getenv("EJECUCION_RESULTADOS_DIR")
DOWNLOAD_DIR: Path = Path(_resultados_dir) if _resultados_dir else Path(os.getenv("DOWNLOAD_DIR", "output/downloads"))
OUTPUT_DIR: Path = Path(_resultados_dir) if _resultados_dir else Path(os.getenv("OUTPUT_DIR", "output/evidencias"))

# ── Configuración del cluster ─────────────────────────────────────────────────
CLUSTER_NAME: str = os.getenv("CLUSTER_NAME", "")

# ── Navegador ─────────────────────────────────────────────────────────────
PAGE_TIMEOUT: int = int(os.getenv("PAGE_TIMEOUT", "60")) * 1000  # Playwright usa ms
HEADLESS: bool = os.getenv("HEADLESS", "False").lower() == "true"
CHROME_PROFILE_DIR: Path = Path(os.getenv("CHROME_PROFILE_DIR", r"C:\Users\iagol\AppData\Local\Google\Chrome\User Data"))
USE_GOOGLE_LOGIN: bool = os.getenv("USE_GOOGLE_LOGIN", "False").lower() == "true"
CHROME_PROFILE_SUBDIR: str = os.getenv("CHROME_PROFILE_SUBDIR", "Default")

# ── Gmail / OTP ───────────────────────────────────────────────────────────────
GMAIL_CLIENT_ID: str = os.getenv("GMAIL_CLIENT_ID", "")
GMAIL_CLIENT_SECRET: str = os.getenv("GMAIL_CLIENT_SECRET", "")
GMAIL_CREDS_PATH: Path = Path(os.getenv("GMAIL_CREDS_PATH", "AuthParaScriptingIago.json"))
GMAIL_TOKEN_PATH: Path = Path(os.getenv("GMAIL_TOKEN_PATH", "token.json"))
OTP_TIMEOUT_SEG: int = int(os.getenv("OTP_TIMEOUT_SEG", "60"))

if GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET:
    _creds = {
        "installed": {
            "client_id": GMAIL_CLIENT_ID,
            "project_id": os.getenv("GMAIL_PROJECT_ID", ""),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_secret": GMAIL_CLIENT_SECRET,
            "redirect_uris": ["http://localhost"],
        }
    }
    GMAIL_CREDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    GMAIL_CREDS_PATH.write_text(json.dumps(_creds), encoding="utf-8")


def validate():
    """Verifica que las variables críticas estén definidas antes de ejecutar."""
    missing = []
    if not MONGO_USER:
        missing.append("MONGO_USER")
    if not MONGO_PASSWORD:
        missing.append("MONGO_PASSWORD")
    if not CLUSTER_NAME:
        missing.append("CLUSTER_NAME")

    if missing:
        raise EnvironmentError(
            f"Faltan las siguientes variables en el archivo .env: {', '.join(missing)}"
        )

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
