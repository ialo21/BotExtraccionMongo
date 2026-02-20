"""
Robot de extracción de logs desde MongoDB Atlas.

Estrategia de ejecución (reunión 5 feb 2026):
  - Se programa dos veces por mes para asegurar la captura completa
    (Mongo Atlas retiene logs solo 30 días).
  - Ejecución ~día 16: descarga los primeros 15 días del mes.
  - Ejecución ~día 1: descarga los últimos días del mes anterior.
"""
import sys
import traceback
from datetime import datetime
from pathlib import Path

import config
from src import browser
from src.dates import get_date_range, format_range_label
import src.mongo_atlas as atlas


def main():
    # Asegurar encoding UTF-8 en consola Windows para logs (evita UnicodeEncodeError)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    # ── Carpetas: respeta vars del orquestador si existen ─────────────────────
    # Orquestador inyecta: EJECUCION_LOGS_DIR y EJECUCION_RESULTADOS_DIR
    import os
    _logs_env = os.getenv("EJECUCION_LOGS_DIR")
    _res_env  = os.getenv("EJECUCION_RESULTADOS_DIR")

    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if _logs_env:
        logs_dir = Path(_logs_env)
    else:
        base = Path("output") / "ejecuciones" / "robot-extraccion-mongo" / run_ts
        logs_dir = base / "logs"

    if _res_env:
        resultados_dir = Path(_res_env)
    else:
        base = Path("output") / "ejecuciones" / "robot-extraccion-mongo" / run_ts
        resultados_dir = base / "resultados"

    logs_dir.mkdir(parents=True, exist_ok=True)
    resultados_dir.mkdir(parents=True, exist_ok=True)

    # run.log siempre en logs/
    log_file = logs_dir / "run.log"

    class Tee:
        def __init__(self, *streams):
            self.streams = streams
        def write(self, data):
            for s in self.streams:
                s.write(data)
        def flush(self):
            for s in self.streams:
                s.flush()

    sys_stdout, sys_stderr = sys.stdout, sys.stderr
    log_handle = open(log_file, "a", encoding="utf-8")
    sys.stdout = Tee(sys_stdout, log_handle)
    sys.stderr = Tee(sys_stderr, log_handle)

    print("=" * 60)
    print("  Robot Extracción Logs - MongoDB Atlas")
    print(f"  Inicio: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("=" * 60)
    print(f"  logs/      → {logs_dir}")
    print(f"  resultados → {resultados_dir}")

    # ── Validar configuración ──────────────────────────────────────────────────
    config.validate()

    start, end = get_date_range()
    print(f"\nRango de extracción: {start} → {end}")

    page = None
    try:
        # ── Abrir navegador ────────────────────────────────────────────────────
        page = browser.launch()

        # ── Paso 1: Login ──────────────────────────────────────────────────────
        # Capturas de login → resultados/
        page = atlas.login(page, resultados_dir, logs_dir)

        # ── Paso 2: Navegar al cluster ─────────────────────────────────────────
        atlas.ir_al_cluster(page, resultados_dir)

        # ── Paso 3: Ir a la sección de logs ───────────────────────────────────
        atlas.ir_a_logs(page, resultados_dir)

        # ── Paso 4: Descargar Audit Log → resultados/ ─────────────────────────
        atlas.descargar_log(page, resultados_dir, tipo_log="audit", start=start, end=end)

        print("\n✓ Proceso completado.")

    except NotImplementedError as e:
        print(f"\n[EN CONSTRUCCIÓN] {e}")
        print("  → Este paso aún no está implementado.")
        print("  → Navegador mantenido abierto para inspección. Ciérralo manualmente.")
        input("  → Presiona ENTER para cerrar el navegador...")
        browser.close()
        sys.exit(0)

    except Exception:
        print("\n[ERROR] Se produjo un error inesperado:")
        traceback.print_exc()
        if page:
            browser.close()
        sys.exit(1)

    finally:
        if log_handle:
            log_handle.flush()
            log_handle.close()
            sys.stdout = sys_stdout
            sys.stderr = sys_stderr

    print(f"\n  Fin: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("=" * 60)


if __name__ == "__main__":
    main()
