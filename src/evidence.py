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

# Deshabilitar el fail-safe de pyautogui (lanza excepción si el mouse está
# en una esquina). En un robot automatizado el mouse puede estar en cualquier
# posición sin que sea una señal de emergencia.
pyautogui.FAILSAFE = False

# Evitar pausa de 0.1s entre cada llamada de pyautogui (innecesaria aquí).
pyautogui.PAUSE = 0


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
        # Mover el cursor al borde izquierdo a media altura: zona sin UI relevante
        # (evita la barra de tareas que activa miniaturas y la esquina superior
        # derecha donde aparece la notificación de descarga de Chrome).
        h = _user32.GetSystemMetrics(1)
        pyautogui.moveTo(0, h // 2, duration=0)
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


def _minimizar_chrome() -> int:
    """Minimiza la ventana de Chrome y devuelve su HWND para restaurarla después."""
    hwnd = _user32.FindWindowW("Chrome_WidgetWin_1", None)
    if hwnd:
        _user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
        _time.sleep(0.3)
    return hwnd or 0


def capturar_propiedades_archivo(output_dir: Path, archivo: Path, nombre_base: str) -> None:
    """
    Abre Explorer en la carpeta de descarga con el archivo seleccionado,
    luego abre Propiedades y captura la pantalla.

    Args:
        output_dir:   Carpeta donde se guardará la captura.
        archivo:      Path al archivo (en su ruta de descarga original).
        nombre_base:  Prefijo para el nombre de la captura.
    """
    # Minimizar Chrome para que no tape Explorer ni Propiedades
    hwnd_chrome = _minimizar_chrome()

    # Abrir Explorer mostrando la carpeta de descarga con el archivo seleccionado
    subprocess.Popen(["explorer", f"/select,{archivo}"])
    _time.sleep(3.0)

    # Forzar foco al Explorer
    hwnd_explorer = _hwnd_explorador_carpeta(archivo.parent)
    _forzar_foco(hwnd_explorer)
    _time.sleep(0.5)

    # Alt+Enter abre Propiedades del archivo seleccionado por /select
    pyautogui.hotkey("alt", "return")

    # Esperar a que aparezca el diálogo de Propiedades y traerlo al frente
    hwnd_props = 0
    for _ in range(25):
        _time.sleep(0.2)
        hwnd_props = _user32.FindWindowW("#32770", None)
        if hwnd_props:
            break

    if hwnd_props:
        _forzar_foco(hwnd_props)
        _time.sleep(0.8)

    capturar(output_dir, f"{nombre_base}_propiedades_archivo")

    # Cerrar Propiedades y Explorer
    if hwnd_props:
        _user32.PostMessageW(hwnd_props, 0x0010, 0, 0)  # WM_CLOSE
    _time.sleep(0.3)
    if hwnd_explorer:
        _user32.PostMessageW(hwnd_explorer, 0x0010, 0, 0)  # WM_CLOSE
    _time.sleep(0.3)

    # Restaurar Chrome
    if hwnd_chrome:
        _user32.ShowWindow(hwnd_chrome, 9)  # SW_RESTORE
