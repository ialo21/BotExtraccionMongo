"""
Gestión de archivos: mover los logs descargados a la carpeta de output,
renombrándolos con la fecha del rango para fácil identificación.
"""
from pathlib import Path
from datetime import date
import shutil
import time


def esperar_descarga(download_dir: Path, timeout: int = 120) -> Path:
    """
    Espera a que aparezca un archivo .gz en la carpeta de descargas.
    Mongo Atlas descarga los logs en formato GZ.

    Args:
        download_dir: Carpeta donde el navegador guarda las descargas.
        timeout: Segundos máximos de espera.

    Returns:
        Path al archivo descargado.

    Raises:
        TimeoutError: Si no aparece ningún archivo en el tiempo indicado.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        gz_files = list(download_dir.glob("*.gz"))
        # Ignorar archivos parciales (.crdownload o similares)
        completos = [f for f in gz_files if not f.suffix.endswith("download")]
        if completos:
            # Esperar un segundo extra para asegurar que el archivo está cerrado
            time.sleep(1)
            return max(completos, key=lambda f: f.stat().st_mtime)
        time.sleep(2)

    raise TimeoutError(f"No se descargó ningún archivo .gz en {timeout} segundos.")


def mover_log(archivo: Path, output_dir: Path, tipo: str, start: date, end: date) -> Path:
    """
    Mueve el log descargado a output_dir con un nombre normalizado.

    Nombre resultante: {tipo}_{YYYYMMDD}_al_{YYYYMMDD}.gz
    Ejemplo:           audit_log_20260201_al_20260215.gz

    Args:
        archivo: Archivo origen (descargado por el navegador).
        output_dir: Carpeta destino.
        tipo: Identificador del tipo de log ("audit_log" o "general_log").
        start: Fecha de inicio del rango.
        end: Fecha de fin del rango.

    Returns:
        Path al archivo en su nueva ubicación.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    nuevo_nombre = f"{tipo}_{start.strftime('%Y%m%d')}_al_{end.strftime('%Y%m%d')}.gz"
    destino = output_dir / nuevo_nombre
    shutil.move(str(archivo), str(destino))
    print(f"  [archivo] Movido → {destino}")
    return destino
