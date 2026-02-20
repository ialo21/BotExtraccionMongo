"""
Captura de pantalla completa del escritorio (pyautogui).
Incluye la barra de tareas de Windows con la hora del sistema.
"""
import subprocess
import time as _time
import pyautogui
from pathlib import Path
from datetime import datetime


def capturar(output_dir: Path, nombre: str, page=None) -> Path:
    """
    Toma una captura de pantalla completa del escritorio y la guarda.
    Usa pyautogui para capturar toda la pantalla, incluyendo el reloj
    de Windows. Si se pasa `page` (Playwright Page), espera brevemente
    a que el frame esté renderizado antes de capturar.

    Args:
        output_dir: Carpeta donde se guardará la imagen.
        nombre: Nombre descriptivo del momento (ej: "login_exitoso").
        page: Playwright Page opcional (solo para sincronizar el render).

    Returns:
        Path al archivo de imagen generado.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = output_dir / f"{timestamp}_{nombre}.png"

    try:
        if page is not None:
            page.wait_for_load_state("domcontentloaded", timeout=5000)
    except Exception:
        pass

    try:
        screenshot = pyautogui.screenshot()
        screenshot.save(str(filename))
    except Exception as e:
        print(f"  [aviso] No se pudo capturar evidencia '{nombre}': {e}")
        return filename

    print(f"  [evidencia] {filename.name}")
    return filename


def capturar_explorador_archivo(output_dir: Path, archivo: Path, nombre_base: str) -> None:
    """
    Toma dos capturas de evidencia post-descarga:
      1. El Explorador de Windows con el archivo seleccionado.
      2. El cuadro de Propiedades del archivo.

    Args:
        output_dir:   Carpeta donde se guardarán las imágenes.
        archivo:      Path al archivo descargado.
        nombre_base:  Prefijo para los nombres de las capturas.
    """
    # 1. Abrir Explorer con el archivo seleccionado
    subprocess.Popen(["explorer", "/select," + str(archivo)])
    _time.sleep(2.5)
    capturar(output_dir, f"{nombre_base}_carpeta_descargas")

    # 2. Abrir Propiedades (Alt+Enter con el archivo ya seleccionado en Explorer)
    pyautogui.hotkey("alt", "return")
    _time.sleep(1.5)
    capturar(output_dir, f"{nombre_base}_propiedades_archivo")

    # Cerrar el cuadro de Propiedades y luego el Explorer
    pyautogui.hotkey("alt", "F4")
    _time.sleep(0.4)
    pyautogui.hotkey("alt", "F4")
    _time.sleep(0.3)
