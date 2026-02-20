"""
Pasos de navegación en MongoDB Atlas.

Cada función representa un paso discreto del proceso y toma una captura
de evidencia al finalizar. Se irán implementando en conjunto con el equipo.
"""
from playwright.sync_api import Page
from datetime import date
from pathlib import Path
import time

import config
from src import browser
from src.evidence import capturar
from src.gmail_otp import obtener_otp


# ── Paso 1: Login ──────────────────────────────────────────────────────────────

def _hacer_login(page: Page, evidencias_dir: Path, logs_dir: Path) -> bool:
    """
    Intenta un ciclo completo de login. Devuelve True si el login fue exitoso.
    """
    page.goto(config.MONGO_ATLAS_URL)
    page.wait_for_load_state("domcontentloaded")

    # Paso 1: Email
    print("  → Ingresando email...")
    page.wait_for_selector("#username", state="visible")
    page.fill("#username", config.MONGO_USER)
    page.click("button:has-text('Next')")

    # Paso 2: Contraseña
    print("  → Ingresando contraseña...")
    page.wait_for_selector("#lg-passwordinput-1", state="visible")
    page.fill("#lg-passwordinput-1", config.MONGO_PASSWORD)

    # Paso 3: Login — un click inicial, espera 300 ms y luego spam Playwright 20s si sigue visible
    print("  → Click inicial en Login y spam si sigue visible...")
    login_btn = page.locator("button:has-text('Login')")
    login_btn.wait_for(state="visible")
    login_btn.scroll_into_view_if_needed()

    # Click inicial
    try:
        login_btn.click(timeout=200, no_wait_after=True)
    except Exception:
        pass

    page.wait_for_timeout(300)

    # Si aún está visible, iniciar spam de 20s
    try:
        login_btn.wait_for(state="visible", timeout=10)
        print("  → Botón sigue visible, iniciando spam Playwright (20s)...")
        start_ts = time.monotonic()
        while time.monotonic() - start_ts < 20:
            try:
                login_btn.click(timeout=50, no_wait_after=True)
            except Exception:
                pass
    except Exception:
        print("  → Botón ya no visible tras el click inicial")

    # Verificación final tras el loop
    try:
        login_btn.wait_for(state="detached", timeout=500)
    except Exception:
        try:
            login_btn.wait_for(state="hidden", timeout=500)
        except Exception:
            pass

    # Paso 4: MFA opcional
    print("  → Verificando si aparece pantalla de MFA...")
    try:
        page.wait_for_selector("button:has-text('Send Code')", timeout=8000)
        print("  → Pantalla MFA detectada. Enviando código...")
        send_ts = time.time()
        page.click("button:has-text('Send Code')")

        otp = obtener_otp(timeout_seg=config.OTP_TIMEOUT_SEG, after_ts=send_ts)

        print(f"  → Rellenando OTP: {otp}")
        inputs = page.query_selector_all("[data-testid='autoAdvanceInput']")
        for i, digito in enumerate(otp):
            inputs[i].click()
            inputs[i].type(digito)

        print("  → OTP ingresado, esperando redirección...")
        capturar(evidencias_dir, "01b_mfa_completado", page)

    except Exception as e:
        if "Send Code" in str(e) or "Timeout" in type(e).__name__:
            print("  → Sin pantalla MFA, continuando...")
        else:
            raise

    # Paso 5: Validar login buscando el botón de organización en el nav
    print("  → Validando login exitoso...")
    try:
        page.wait_for_selector(
            "[data-testid='lg-cloud_nav-top_nav-resource_nav-segment-button']",
            timeout=config.PAGE_TIMEOUT,
        )
        return True
    except Exception:
        capturar(evidencias_dir, "01_login_fallido", page)
        return False


def _hacer_login_google(page: Page, evidencias_dir: Path, logs_dir: Path) -> bool:
    """
    Login via SSO de Google: navega a Atlas, pulsa el botón de Google
    y espera la redirección al dashboard (la sesión de Chrome ya está activa).
    """
    page.goto(config.MONGO_ATLAS_URL)

    print("  → Buscando botón de Google...")
    google_btn = None
    for i in range(6):  # hasta ~30s
        try:
            google_btn = page.wait_for_selector("button[data-lgid='lg-button']:has-text('Google')", timeout=5000)
            break
        except Exception:
            page.wait_for_timeout(1000)
    if not google_btn:
        capturar(evidencias_dir, "01_login_google_no_encontrado", page)
        return False
    google_btn.click()

    print("  → Esperando redirección al dashboard...")
    try:
        page.wait_for_url("**/cloud.mongodb.com/**", timeout=config.PAGE_TIMEOUT)
        return True
    except Exception:
        pass
    try:
        page.wait_for_selector(
            "[data-testid='lg-cloud_nav-top_nav-resource_nav-segment-button']",
            timeout=10000,
        )
        return True
    except Exception:
        capturar(evidencias_dir, "01_login_google_fallido", page)
        return False


def login(page: Page, evidencias_dir: Path, logs_dir: Path, max_reintentos: int = 3) -> Page:
    """
    Navega a MongoDB Atlas e inicia sesión. Si el login falla, reintenta.
    
    Flujo:
    1. Ingresar email → Next
    2. Ingresar contraseña → Login
    3. MFA: Send Code → leer OTP del correo → rellenar 6 dígitos
    4. Validar presencia del botón de organización en el nav
    5. Si falla: captura evidencia y reintenta hasta max_reintentos
    """
    print("[1/N] Accediendo a MongoDB Atlas...")

    for intento in range(1, max_reintentos + 1):
        if intento > 1:
            print(f"  → Reintento {intento}/{max_reintentos} con navegador nuevo...")
            browser.close()
            page = browser.launch()

        if config.USE_GOOGLE_LOGIN:
            exito = _hacer_login_google(page, evidencias_dir, logs_dir)
        else:
            exito = _hacer_login(page, evidencias_dir, logs_dir)

        if exito:
            capturar(evidencias_dir, "01_login_exitoso", page)
            print("  ✓ Login completado")
            return page

        print(f"  ✗ Login fallido en intento {intento}.")

    # Evidencia final en carpeta logs de la ejecución
    capturar(logs_dir, "login_fallido_final", page)
    raise RuntimeError("Login fallido tras todos los reintentos. Revisar evidencias en logs/.")


# ── Paso 2: Navegar al cluster ─────────────────────────────────────────────────

def ir_al_cluster(page: Page, evidencias_dir: Path) -> None:
    """
    Desde el dashboard:
    1. Cambia a la organización Interseguro
    2. Entra al proyecto PortalSistemas
    3. Navega a Clusters en el menú lateral
    4. Localiza el cluster vis-data-prd
    5. Abre el menú ... y hace clic en Download Logs
    """
    print("[2/N] Cambiando a organización Interseguro...")

    # Abrir selector de organización
    page.click("[data-testid='lg-cloud_nav-top_nav-resource_nav-segment-button']")

    # Seleccionar Interseguro en el dropdown
    page.click("a[aria-label='Interseguro']")
    page.wait_for_load_state("domcontentloaded")
    capturar(evidencias_dir, "02a_org_interseguro", page)
    print("  ✓ Organización Interseguro seleccionada")

    # Hacer clic en el proyecto PortalSistemas
    print("  → Entrando al proyecto PortalSistemas...")
    page.click("a[href*='66ba761f5acbaa376da8f5b3']")
    page.wait_for_load_state("domcontentloaded")
    capturar(evidencias_dir, "02b_proyecto_portalsistemas", page)
    print("  ✓ Proyecto PortalSistemas abierto")

    # Clic en Clusters en el menú lateral
    print("  → Navegando a Clusters...")
    page.click("[data-testid='lg-cloud_nav-side_nav-clusters']")
    page.wait_for_load_state("domcontentloaded")
    capturar(evidencias_dir, "02c_clusters", page)
    print("  ✓ Sección Clusters abierta")

    # Localizar el cluster vis-data-prd y abrir su menú ...
    print("  → Localizando cluster vis-data-prd...")
    cluster_row = page.locator(
        "css=[data-testid='cluster-name-detail-link'][href*='vis-data-prd']"
        " >> xpath=ancestor::div[contains(@class,'e15qq9hb5')]"
    ).first
    dropdown_btn = cluster_row.locator("[data-testid='Dropdown_toggleButton']").first
    dropdown_btn.click()
    capturar(evidencias_dir, "02d_menu_cluster", page)
    print("  ✓ Menú del cluster abierto")

    # Clic en Download Logs
    print("  → Haciendo clic en Download Logs...")
    page.click("a.dropdown-component-link:has-text('Download Logs')")
    page.wait_for_load_state("domcontentloaded")
    capturar(evidencias_dir, "02e_download_logs", page)
    print("  ✓ Sección Download Logs abierta")


# ── Paso 3: Ir a la sección de descarga de logs (fusionado en ir_al_cluster) ───

def ir_a_logs(page: Page, evidencias_dir: Path) -> None:
    """
    Stub mantenido por compatibilidad con main.py.
    La navegación a logs ya ocurre al final de ir_al_cluster.
    """
    pass


# ── Paso 4: Configurar filtro de fechas y descargar ────────────────────────────

# Mapeo tipo_log → valor del <select name="processes">
_PROCESS_VALUE = {
    "audit":   "mongodb-audit-log",
    "general": "mongodb",
}

# Formato de fecha que acepta el datepicker del modal (ej: "Mon Feb 16 2026")
_DATE_FMT = "%a %b %d %Y"


def _set_date_input(page: Page, selector: str, valor: str) -> None:
    """
    Escribe en un input de fecha del modal.
    1. Click en el campo para enfocarlo.
    2. Ctrl+A + Delete para limpiar.
    3. type() carácter a carácter.
    4. Si queda vacío, JS fallback.
    5. NO presiona Tab (lo borra en este datepicker); confirma con Escape.
    """
    inp = page.locator(selector)
    inp.click()
    page.wait_for_timeout(200)
    page.keyboard.press("Control+a")
    page.keyboard.press("Delete")
    page.wait_for_timeout(100)
    inp.type(valor)
    page.wait_for_timeout(200)

    # Verificar si el valor quedó establecido
    actual = inp.input_value()
    if not actual:
        page.evaluate(
            """([sel, val]) => {
                const el = document.querySelector(sel);
                if (!el) return;
                const setter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value'
                ).set;
                setter.call(el, val);
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
            }""",
            [selector, valor],
        )
        page.wait_for_timeout(100)

    # Confirmar sin Tab (Tab borra el valor en este datepicker)
    page.keyboard.press("Escape")
    page.wait_for_timeout(100)


def _set_time_input(page: Page, container_selector: str, valor: str) -> None:
    """Limpia y escribe en un input de hora del modal."""
    inp = page.locator(f"{container_selector} [data-testid='time-picker-input']")
    inp.click()
    inp.fill("")
    inp.type(valor)
    inp.press("Enter")


def descargar_log(
    page: Page,
    evidencias_dir: Path,
    tipo_log: str,
    start: date,
    end: date,
) -> None:
    """
    En el modal Download Logs:
    1. Selecciona el proceso (audit o general)
    2. Selecciona Custom Time
    3. Ingresa fecha/hora de inicio (12:00am) y fin (11:30pm)
    4. Hace clic en Download Logs

    Args:
        tipo_log: "audit" o "general"
        start:    Fecha de inicio del rango.
        end:      Fecha de fin del rango.
    """
    process_value = _PROCESS_VALUE.get(tipo_log)
    if process_value is None:
        raise ValueError(f"tipo_log inválido: {tipo_log!r}. Usa 'audit' o 'general'.")

    print(f"[4/N] Descargando {tipo_log} log ({start} → {end})...")

    # 1. Seleccionar proceso
    print(f"  → Seleccionando proceso: {process_value}...")
    page.select_option("select[name='processes']", value=process_value)

    # 2. Seleccionar Custom Time en Time Period
    print("  → Seleccionando Custom Time...")
    page.select_option("select[name='timePeriods']", value="Custom Time")

    # 3. Fechas: formato "Sun Feb 01 2026"
    start_str = start.strftime(_DATE_FMT)
    end_str   = end.strftime(_DATE_FMT)

    print(f"  → Ingresando fecha inicio: {start_str} 12:00am...")
    _set_date_input(page, "input[name='startDate']", start_str)
    _set_time_input(page, ".js-start-time-container", "12:00am")

    print(f"  → Ingresando fecha fin: {end_str} 11:30pm...")
    _set_date_input(page, "input[name='endDate']", end_str)
    _set_time_input(page, ".js-end-time-container", "11:30pm")

    capturar(evidencias_dir, f"04_filtro_{tipo_log}_log", page)

    # 4. Descargar
    print("  → Haciendo clic en Download Logs...")
    with page.expect_download() as dl_info:
        page.click("button[data-testid='download-logs-modal']")

    descarga = dl_info.value
    nombre = f"{tipo_log}_log_{start.strftime('%Y%m%d')}_al_{end.strftime('%Y%m%d')}.gz"
    destino = evidencias_dir / nombre
    descarga.save_as(str(destino))

    capturar(evidencias_dir, f"05_descarga_completada_{tipo_log}_log", page)
    print(f"  ✓ Descarga guardada: {destino}")
