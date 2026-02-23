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


_PS_ACTIVATE_EXPLORER = """\
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class Win32 {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
}
'@
$procs = Get-Process -Name explorer -ErrorAction SilentlyContinue |
         Where-Object { $_.MainWindowHandle -ne 0 } |
         Sort-Object StartTime -Descending
if ($procs) {
    $h = $procs[0].MainWindowHandle
    [Win32]::ShowWindow($h, 9)   # SW_RESTORE
    [Win32]::SetForegroundWindow($h)
}
"""


def _activar_explorador() -> None:
    """Fuerza el foco al Explorador de Windows más reciente via PowerShell."""
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", _PS_ACTIVATE_EXPLORER],
            capture_output=True,
            timeout=5,
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
    # 1. Abrir Explorer con el archivo seleccionado
    subprocess.Popen(["explorer", f"/select,{archivo}"])
    _time.sleep(2.5)

    # Forzar foco al Explorador (el navegador Playwright puede haberlo quedado en primer plano)
    _activar_explorador()
    _time.sleep(0.8)
    capturar(output_dir, f"{nombre_base}_carpeta_descargas")

    # 2. Abrir Propiedades con Explorer ya en foco (Alt+Enter sobre el archivo seleccionado)
    pyautogui.hotkey("alt", "return")
    _time.sleep(2.0)
    capturar(output_dir, f"{nombre_base}_propiedades_archivo")

    # Cerrar Propiedades y luego Explorer
    pyautogui.hotkey("alt", "F4")
    _time.sleep(0.5)
    pyautogui.hotkey("alt", "F4")
    _time.sleep(0.3)
