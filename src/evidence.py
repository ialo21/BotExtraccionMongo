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
_kernel32 = ctypes.windll.kernel32
_shell32 = ctypes.windll.shell32

# LANGID: primario = low 10 bits. 9 = inglés, 10 = español.
_LANG_SPANISH = 10


def _verbo_propiedades() -> str:
    """Devuelve el verbo de Shell para abrir Propiedades según el idioma de la UI de Windows."""
    try:
        lang = _kernel32.GetUserDefaultUILanguage()
        if (lang & 0x3FF) == _LANG_SPANISH:
            return "propiedades"
    except Exception:
        pass
    return "properties"

# Tipo callback requerido por EnumWindows
_WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_size_t, ctypes.c_size_t)


def _hwnd_explorador_carpeta(carpeta: Path) -> int:
    """
    Busca la ventana del Explorador de Windows que muestra la carpeta dada
    comparando el nombre de carpeta contra el título de cada ventana CabinetWClass.
    Si no encuentra ninguna coincidencia devuelve la primera CabinetWClass disponible.
    """
    nombre = carpeta.name.lower()
    resultado = [0]

    def _cb(hwnd, _):
        if not _user32.IsWindowVisible(hwnd):
            return True
        cls = ctypes.create_unicode_buffer(64)
        _user32.GetClassNameW(hwnd, cls, 64)
        if cls.value not in ("CabinetWClass", "ExploreWClass"):
            return True
        titulo = ctypes.create_unicode_buffer(512)
        _user32.GetWindowTextW(hwnd, titulo, 512)
        if nombre in titulo.value.lower():
            resultado[0] = hwnd
            return False  # detener enumeración
        return True

    cb = _WNDENUMPROC(_cb)
    _user32.EnumWindows(cb, 0)

    if not resultado[0]:
        resultado[0] = _user32.FindWindowW("CabinetWClass", None) or 0
    return resultado[0]


def _forzar_foco(hwnd: int) -> None:
    """
    Fuerza el foco al HWND dado aunque el proceso Python no sea el proceso en
    primer plano. Usa AttachThreadInput para obtener permiso de SetForegroundWindow.
    """
    if not hwnd:
        return
    tid_actual = _kernel32.GetCurrentThreadId()
    tid_destino = _user32.GetWindowThreadProcessId(hwnd, None)
    adjuntado = False
    if tid_actual != tid_destino:
        adjuntado = bool(_user32.AttachThreadInput(tid_actual, tid_destino, True))
    _user32.ShowWindow(hwnd, 9)          # SW_RESTORE
    _user32.BringWindowToTop(hwnd)
    _user32.SetForegroundWindow(hwnd)
    if adjuntado:
        _user32.AttachThreadInput(tid_actual, tid_destino, False)


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

    # Encontrar la ventana del Explorador por nombre de carpeta y forzar foco
    hwnd = _hwnd_explorador_carpeta(archivo.parent)
    _forzar_foco(hwnd)
    _time.sleep(0.8)
    capturar(output_dir, f"{nombre_base}_carpeta_descargas")

    # 2. Abrir Propiedades directamente via Windows Shell API.
    #    Verbo según idioma de la UI; si falla (código <= 32), probar el otro.
    verb = _verbo_propiedades()
    otro = "propiedades" if verb == "properties" else "properties"
    r = _shell32.ShellExecuteW(None, verb, str(archivo), None, str(archivo.parent), 1)
    if r <= 32:
        _shell32.ShellExecuteW(None, otro, str(archivo), None, str(archivo.parent), 1)
    _time.sleep(3.0)
    capturar(output_dir, f"{nombre_base}_propiedades_archivo")

    # Cerrar Propiedades y luego Explorer
    pyautogui.hotkey("alt", "F4")
    _time.sleep(0.5)
    pyautogui.hotkey("alt", "F4")
    _time.sleep(0.3)
