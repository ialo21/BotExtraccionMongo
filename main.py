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
from src.evidence import capturar
import src.mongo_atlas as atlas
from src.ipe import generar_ipe
from src.drive import subir_resultados_a_drive, subir_archivo_a_drive


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
    _PROJECT_ROOT = Path(__file__).resolve().parent
    _logs_env = (os.getenv("EJECUCION_LOGS_DIR") or "").strip()
    _res_env  = (os.getenv("EJECUCION_RESULTADOS_DIR") or "").strip()

    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    def _to_abs(raw: str, default_relative: str) -> Path:
        """Convierte a Path absoluto; si está vacío usa default anclado al proyecto."""
        if not raw:
            return _PROJECT_ROOT / default_relative
        p = Path(raw)
        return p if p.is_absolute() else _PROJECT_ROOT / p

    logs_dir      = _to_abs(_logs_env, f"output/ejecuciones/robot-extraccion-mongo/{run_ts}/logs")
    resultados_dir = _to_abs(_res_env,  f"output/ejecuciones/robot-extraccion-mongo/{run_ts}/resultados")

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
    print(f"  [config] HEADLESS={config.HEADLESS} (env raw: {os.getenv('HEADLESS', 'NO_SET')})")

    start, end = get_date_range()
    print(f"\nRango de extracción: {start} → {end}")

    page = None
    try:
        # ── Abrir navegador ────────────────────────────────────────────────────
        page = browser.launch()

        # ── Paso 1: Login ──────────────────────────────────────────────────────
        # Capturas de login → logs/ (no son evidencia final del proceso)
        page = atlas.login(page, logs_dir, logs_dir)

        # ── Paso 2: Navegar al cluster ─────────────────────────────────────────
        # Capturas de navegación → logs/
        atlas.ir_al_cluster(page, logs_dir)

        # ── Paso 3: Ir a la sección de logs ───────────────────────────────────
        atlas.ir_a_logs(page, logs_dir)

        # ── Paso 4: Descargar mongod-audit-log ────────────────────────────────
        carpeta_audit = resultados_dir / "mongod-audit-log"
        carpeta_audit.mkdir(parents=True, exist_ok=True)
        capturas_audit = atlas.descargar_log(page, carpeta_audit, tipo_log="audit", start=start, end=end)

        # Preparar datos comunes para IPEs
        import os
        rango_label = f"{start.strftime('%d%m')}-{end.strftime('%d%m')}"
        plantilla = _PROJECT_ROOT / "assets" / "CDBD_IPE_MongoAtlas_.xlsx"

        # ── Paso 6: Descargar mongod ──────────────────────────────────────────
        carpeta_general = resultados_dir / "mongod"
        carpeta_general.mkdir(parents=True, exist_ok=True)
        capturas_general = atlas.descargar_log(page, carpeta_general, tipo_log="general", start=start, end=end)

        browser.close()
        
        # ── Paso 5: Subir resultados a Google Drive ──────────────────────────────
        drive_urls = subir_resultados_a_drive(resultados_dir, run_ts, start, end) or {}
        
        # ── Paso 6: Generar IPE para mongod-audit-log ─────────────────────────
        print("\n[6/N] Generando IPE para mongod-audit-log...")
        
        if plantilla.exists():
            datos_ipe_audit = {
                "I3": datetime.now().strftime("%d/%m/%Y"),
                "F4": os.getlogin(),
                "F5": f"El objetivo principal de la extracción es identificar los cambios realizados en la información de las bases de datos durante el periodo {start.strftime('%d/%m/%Y')} - {end.strftime('%d/%m/%Y')}.",
                "C11": "x",
                "C17": "x",
            }
            salida_ipe_audit = carpeta_audit / f"CDBD_IPE_MongoAtlas_mongod-audit-log_{rango_label}.xlsx"
            
            try:
                generar_ipe(
                    plantilla_path=plantilla,
                    salida_path=salida_ipe_audit,
                    datos=datos_ipe_audit,
                    imagenes=capturas_audit,
                    hoja="Hoja 1",
                    fila_base_img=26,
                    col_img="D",
                    espaciado_filas=36,
                    drive_url=(drive_urls.get("mongod-audit-log") or {}).get("url"),
                )
            except Exception as e:
                print(f"  [aviso] No se pudo generar IPE para mongod-audit-log: {e}")
            else:
                try:
                    carpeta_audit_id = (drive_urls.get("mongod-audit-log") or {}).get("id")
                    if carpeta_audit_id:
                        subir_archivo_a_drive(salida_ipe_audit, carpeta_audit_id)
                        print("  ✓ IPE mongod-audit-log subida a Drive")
                except Exception as e:
                    print(f"  [aviso] No se pudo subir IPE mongod-audit-log a Drive: {e}")
        else:
            print(f"  [aviso] Plantilla IPE no encontrada en: {plantilla}")
        
        # ── Paso 7: Generar IPE para mongod ───────────────────────────────────
        print("\n[7/N] Generando IPE para mongod...")
        
        if plantilla.exists():
            datos_ipe_general = {
                "I3": datetime.now().strftime("%d/%m/%Y"),
                "F4": os.getlogin(),
                "F5": f"El objetivo principal de la extracción es identificar los cambios realizados en la información de las bases de datos durante el periodo {start.strftime('%d/%m/%Y')} - {end.strftime('%d/%m/%Y')}.",
                "C11": "x",
                "C17": "x",
            }
            salida_ipe_general = carpeta_general / f"CDBD_IPE_MongoAtlas_mongod_{rango_label}.xlsx"
            
            try:
                generar_ipe(
                    plantilla_path=plantilla,
                    salida_path=salida_ipe_general,
                    datos=datos_ipe_general,
                    imagenes=capturas_general,
                    hoja="Hoja 1",
                    fila_base_img=26,
                    col_img="D",
                    espaciado_filas=36,
                    drive_url=(drive_urls.get("mongod") or {}).get("url"),
                )
            except Exception as e:
                print(f"  [aviso] No se pudo generar IPE para mongod: {e}")
            else:
                try:
                    carpeta_mongod_id = (drive_urls.get("mongod") or {}).get("id")
                    if carpeta_mongod_id:
                        subir_archivo_a_drive(salida_ipe_general, carpeta_mongod_id)
                        print("  ✓ IPE mongod subida a Drive")
                except Exception as e:
                    print(f"  [aviso] No se pudo subir IPE mongod a Drive: {e}")
        
        # ── Paso 8: Guardar URL de Drive para el orquestador ─────────────────────
        if drive_urls and drive_urls.get("execution_folder"):
            drive_url_file = resultados_dir / "drive_url.txt"
            try:
                drive_url_file.write_text(drive_urls["execution_folder"]["url"], encoding="utf-8")
                print(f"  ✓ URL de Drive guardada en: {drive_url_file.name}")
            except Exception as e:
                print(f"  [aviso] No se pudo guardar drive_url.txt: {e}")
        
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
            try:
                capturar(logs_dir, "error_inesperado", page)
            except Exception:
                pass
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
