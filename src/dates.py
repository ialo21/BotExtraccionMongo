"""
Lógica para calcular los rangos de fechas de descarga.

Estrategia de quincenas completas:
  - Ejecución entre día 1 y 15  → segunda quincena del mes anterior (16 → último día).
  - Ejecución entre día 16 y 31 → primera quincena del mes actual  ( 1 → 15).

Siempre se coge la última quincena cerrada, independientemente del día exacto
dentro de cada mitad del mes.

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
    Si no, calcula automáticamente según el día de ejecución actual:

      - Días  1-15 del mes → del 16 al último día del mes anterior.
      - Días 16-31 del mes → del  1 al 15 del mes actual.
    """
    env_desde = os.getenv("BOT_INPUT_FECHA_DESDE", "").strip()
    env_hasta = os.getenv("BOT_INPUT_FECHA_HASTA", "").strip()

    if env_desde and env_hasta:
        start = date.fromisoformat(env_desde)
        end = date.fromisoformat(env_hasta)
        print(f"  [fechas] Usando rango del orquestador: {start} → {end}")
        return start, end

    today = date.today()

    if today.day <= 15:
        # Segunda quincena del mes anterior: del 16 al último día
        first_of_current = today.replace(day=1)
        last_of_prev = first_of_current - timedelta(days=1)
        start = last_of_prev.replace(day=16)
        end   = last_of_prev
    else:
        # Primera quincena del mes actual: del 1 al 15
        start = today.replace(day=1)
        end   = today.replace(day=15)

    print(f"  [fechas] Rango automático: {start} → {end}")
    return start, end


def format_range_label(start: date, end: date) -> str:
    """Genera una etiqueta legible para usar en nombres de archivo."""
    return f"{start.strftime('%Y%m%d')}_al_{end.strftime('%Y%m%d')}"
