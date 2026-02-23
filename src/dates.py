"""
Lógica para calcular los rangos de fechas de descarga.

Estrategia definida en reunión (5 feb 2026):
  - Ejecución 1 (~día 16): cubre del día 1 al día anterior a la ejecución.
  - Ejecución 2 (~día 1 del mes siguiente): cubre del día 16 al último día del mes anterior.

La función get_date_range() detecta automáticamente qué rango corresponde
según el día de ejecución actual, salvo que el orquestador inyecte
BOT_INPUT_FECHA_DESDE y BOT_INPUT_FECHA_HASTA como variables de entorno.
"""
from datetime import date, timedelta
import calendar
import os


def get_date_range() -> tuple[date, date]:
    """
    Devuelve (fecha_inicio, fecha_fin).

    Si existen las variables de entorno BOT_INPUT_FECHA_DESDE y
    BOT_INPUT_FECHA_HASTA (formato YYYY-MM-DD), las usa directamente.
    Si no, calcula automáticamente según el día de ejecución actual.
    """
    env_desde = os.getenv("BOT_INPUT_FECHA_DESDE", "").strip()
    env_hasta = os.getenv("BOT_INPUT_FECHA_HASTA", "").strip()

    if env_desde and env_hasta:
        start = date.fromisoformat(env_desde)
        end = date.fromisoformat(env_hasta)
        print(f"  [fechas] Usando rango del orquestador: {start} → {end}")
        return start, end

    today = date.today()

    if today.day == 1:
        prev_month = today.replace(day=1) - timedelta(days=1)
        start = prev_month.replace(day=16)
        end = prev_month
        return start, end

    if 2 <= today.day <= 16:
        start = today.replace(day=1)
        end = today - timedelta(days=1)
    else:
        start = today.replace(day=16)
        end = today - timedelta(days=1)

    return start, end


def format_range_label(start: date, end: date) -> str:
    """Genera una etiqueta legible para usar en nombres de archivo."""
    return f"{start.strftime('%Y%m%d')}_al_{end.strftime('%Y%m%d')}"
