"""
Captura de pantalla completa del escritorio (pyautogui).
Incluye la barra de tareas de Windows con la hora del sistema.
"""
import ctypes
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


_user32 = ctypes.windll.user32
_shell32 = ctypes.windll.shell32


def _hwnd_explorador() -> int:
    """Devuelve el HWND de la ventana del Explorador de Windows abierta (clase CabinetWClass)."""
    hwnd = _user32.FindWindowW("CabinetWClass", None)
    return hwnd or 0


def _activar_ventana(hwnd: int) -> None:
    """Restaura y trae al frente la ventana indicada."""
    if hwnd:
        _user32.ShowWindow(hwnd, 9)   # SW_RESTORE
        _user32.SetForegroundWindow(hwnd)


def _abrir_propiedades(archivo: Path, hwnd_padre: int) -> None:
    """
    Abre el diálogo de Propiedades del archivo via ShellExecuteW con el HWND
    del Explorador como ventana padre, garantizando que aparezca en primer plano.
    """
    try:
        _shell32.ShellExecuteW(
            hwnd_padre,          # padre → el diálogo aparece encima del Explorer
            "properties",        # verb
            str(archivo),        # archivo
            None,                # parámetros
            str(archivo.parent), # directorio
            1,                   # SW_SHOWNORMAL
        )
    except Exception:
        pass


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
    # 1. Abrir Explorer con el archivo seleccionado y esperar a que cargue
    subprocess.Popen(["explorer", f"/select,{archivo}"])
    _time.sleep(3.0)

    # Traer Explorer al frente y capturar
    hwnd = _hwnd_explorador()
    _activar_ventana(hwnd)
    _time.sleep(0.8)
    capturar(output_dir, f"{nombre_base}_carpeta_descargas")

    # 2. Abrir Propiedades con Explorer como padre (aparece encima de Chrome)
    _abrir_propiedades(archivo, hwnd)
    _time.sleep(2.5)
    capturar(output_dir, f"{nombre_base}_propiedades_archivo")

    # Cerrar Propiedades y luego Explorer
    pyautogui.hotkey("alt", "F4")
    _time.sleep(0.5)
    pyautogui.hotkey("alt", "F4")
    _time.sleep(0.3)
