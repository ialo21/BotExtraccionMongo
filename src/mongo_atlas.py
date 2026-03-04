"""
Pasos de navegación en MongoDB Atlas.

Cada función representa un paso discreto del proceso y toma una captura
de evidencia al finalizar. Se irán implementando en conjunto con el equipo.
"""
from playwright.sync_api import Page
from datetime import date, datetime
from pathlib import Path
import ctypes
import struct
import json
import shutil
import time
import random

import config
from src import browser
from src.anticaptcha import resolver_recaptcha
from src.evidence import capturar, capturar_propiedades_archivo
from src.gmail_otp import obtener_otp


# ── Helpers de humanización ────────────────────────────────────────────────────

def _random_sleep(min_s: float = 0.8, max_s: float = 2.0) -> None:
    """Pausa aleatoria que simula el tiempo de lectura/reflexión de un humano."""
    time.sleep(random.uniform(min_s, max_s))


def _fast_fill(page: Page, selector: str, text: str) -> None:
    """Rellena un campo instantáneamente. Anti-Captcha maneja la validación de bot."""
    page.locator(selector).fill(text)


def _human_click(page: Page, locator, scroll_first: bool = True) -> None:
    """
    Mueve el mouse hacia el elemento y hace click con un leve desplazamiento
    aleatorio para no aterrizar siempre en el centro exacto.
    """
    if scroll_first:
        try:
            locator.scroll_into_view_if_needed(timeout=3000)
            page.wait_for_timeout(random.randint(60, 150))
        except Exception:
            pass

    box = locator.bounding_box()
    if box:
        tx = box["x"] + box["width"] * random.uniform(0.3, 0.7)
        ty = box["y"] + box["height"] * random.uniform(0.3, 0.7)
        page.mouse.move(tx, ty, steps=random.randint(4, 8))
        page.wait_for_timeout(random.randint(20, 60))
        page.mouse.click(tx, ty)
    else:
        locator.click()


# ── Paso 1: Login ──────────────────────────────────────────────────────────────

def _hacer_login(page: Page, evidencias_dir: Path, logs_dir: Path) -> bool:
    """
    Intenta un ciclo completo de login con comportamiento humanizado.
    Devuelve True si el login fue exitoso.
    """
    page.goto(config.MONGO_ATLAS_URL)
    page.wait_for_load_state("domcontentloaded")

    # Paso 1: Email
    print("  → Ingresando email...")
    page.wait_for_selector("#username", state="visible")
    _fast_fill(page, "#username", config.MONGO_USER)

    next_btn = page.locator("button:has-text('Next')")
    next_btn.wait_for(state="visible")
    _human_click(page, next_btn)
    _random_sleep(0.5, 1.0)

    # Paso 2: Contraseña — inyectar hook ANTES de escribir para que esté listo
    print("  → Ingresando contraseña...")
    page.wait_for_selector("#lg-passwordinput-1", state="visible")

    # Instalar hook de intercepción INMEDIATAMENTE al cargar la pantalla de contraseña.
    # Esto sobreescribe grecaptcha.enterprise.execute ANTES de que el formulario lo llame,
    # y también instala un polling que re-aplica el override si reCAPTCHA se reinicializa.
    page.evaluate("""() => {
        window.__ANTICAPTCHA_TOKEN__ = null;
        function patchExecute() {
            if (window.grecaptcha && window.grecaptcha.enterprise &&
                window.grecaptcha.enterprise.execute &&
                !window.grecaptcha.enterprise.__patched) {
                const _orig = window.grecaptcha.enterprise.execute.bind(window.grecaptcha.enterprise);
                window.grecaptcha.enterprise.execute = function(siteKey, opts) {
                    if (window.__ANTICAPTCHA_TOKEN__) {
                        console.log('[anti-captcha] Returning injected token for action:', opts?.action);
                        window.__CAPTCHA_ACTION__ = opts?.action || '';
                        return Promise.resolve(window.__ANTICAPTCHA_TOKEN__);
                    }
                    return _orig(siteKey, opts);
                };
                window.grecaptcha.enterprise.__patched = true;
            }
        }
        patchExecute();
        window.__patchInterval = setInterval(patchExecute, 500);
    }""")
    print("  → Hook de grecaptcha.enterprise.execute instalado")

    _fast_fill(page, "#lg-passwordinput-1", config.MONGO_PASSWORD)

    # Paso 3: Capturar el action real que usa la página (si execute ya fue llamado)
    detected_action = page.evaluate("() => window.__CAPTCHA_ACTION__ || null")
    captcha_action = detected_action or "login"
    print(f"  → pageAction detectado: {detected_action!r} (usando: {captcha_action!r})")

    # Resolver reCAPTCHA Enterprise v3 con Anti-Captcha
    print("  → Resolviendo reCAPTCHA Enterprise v3 (Anti-Captcha)...")
    captcha_token = resolver_recaptcha(
        page_url=config.MONGO_ATLAS_URL,
        site_key=config.RECAPTCHA_SITE_KEY,
        action=captcha_action,
    )
    print("  → Token obtenido, inyectando...")

    # Setear el token para que el hook de execute lo devuelva cuando Login haga submit
    page.evaluate("(token) => { window.__ANTICAPTCHA_TOKEN__ = token; }", captcha_token)

    # También inyectar en campos del DOM como fallback
    page.evaluate("""(token) => {
        document.querySelectorAll('[name="g-recaptcha-response"]').forEach(
            el => { el.value = token; }
        );
        const tokenInput = document.querySelector('#recaptcha-token');
        if (tokenInput) {
            const setter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value'
            ).set;
            setter.call(tokenInput, token);
            tokenInput.dispatchEvent(new Event('input', { bubbles: true }));
            tokenInput.dispatchEvent(new Event('change', { bubbles: true }));
        }
    }""", captcha_token)

    # Interceptor de requests como última línea de defensa
    def _swap_captcha_token(route):
        request = route.request
        if request.method != "POST" or not request.post_data:
            route.continue_()
            return
        try:
            body = json.loads(request.post_data)
            modified = False
            for key in list(body.keys()):
                val = body[key]
                if isinstance(val, str) and len(val) > 100:
                    if any(t in key.lower() for t in ("captcha", "recaptcha")):
                        body[key] = captcha_token
                        modified = True
                        print(f"  → [interceptor] Token reemplazado en '{key}'")
            if modified:
                response = route.fetch(post_data=json.dumps(body))
                print(f"  → [interceptor] Respuesta: {response.status}")
                try:
                    print(f"  → [interceptor] Body: {response.text()[:500]}")
                except Exception:
                    pass
                route.fulfill(response=response)
                return
        except (json.JSONDecodeError, TypeError):
            pass
        route.continue_()

    page.route("https://account.mongodb.com/**", _swap_captcha_token)

    # Paso 4: Click en Login
    _random_sleep(0.2, 0.4)
    print("  → Haciendo clic en Login...")
    login_btn = page.locator("button:has-text('Login')")
    login_btn.wait_for(state="visible")
    _human_click(page, login_btn)

    try:
        login_btn.wait_for(state="hidden", timeout=20_000)
        print("  → Formulario procesado")
    except Exception:
        print("  → Botón Login aún visible, continuando de todas formas...")

    # Limpiar hook e interceptor
    page.evaluate("() => { clearInterval(window.__patchInterval); }")
    try:
        page.unroute("https://account.mongodb.com/**", _swap_captcha_token)
    except Exception:
        pass

    _random_sleep(0.4, 0.8)

    # Paso 5: MFA opcional
    print("  → Verificando si aparece pantalla de MFA...")
    mfa_detectado = False
    try:
        page.wait_for_selector("button:has-text('Send Code')", timeout=8000)
        mfa_detectado = True
    except Exception:
        print("  → Sin pantalla MFA, continuando...")

    if mfa_detectado:
        print("  → Pantalla MFA detectada. Enviando código...")

        send_btn = page.locator("button:has-text('Send Code')")
        send_ts = time.time()
        _human_click(page, send_btn)
        print(f"  → Código solicitado. Timestamp de envío: {send_ts:.3f}")

        # Cualquier excepción aquí (incluido TimeoutError del correo) es un
        # error real dentro del flujo MFA — NO debe silenciarse.
        otp = obtener_otp(timeout_seg=config.OTP_TIMEOUT_SEG, after_ts=send_ts)

        print(f"  → Rellenando OTP: {otp}")
        inputs = page.query_selector_all("[data-testid='autoAdvanceInput']")
        print(f"  → Inputs OTP encontrados: {len(inputs)}")
        for i, digito in enumerate(otp):
            inputs[i].click()
            inputs[i].type(digito)
            page.wait_for_timeout(50)

        print("  → OTP ingresado, esperando redirección...")
        _random_sleep(1.0, 2.0)

    # Paso 5b: Descartar popup "Set up another MFA method" si aparece
    try:
        remind_btn = page.locator("button[name='snooze']")
        remind_btn.wait_for(state="visible", timeout=5_000)
        print("  → Pantalla 'Set up another MFA method' detectada. Haciendo clic en 'Remind me later'...")
        _human_click(page, remind_btn)
        _random_sleep(0.5, 1.0)
    except Exception:
        pass

    # Paso 6: Validar login buscando el botón de organización en el nav
    print("  → Validando login exitoso...")
    try:
        page.wait_for_selector(
            "[data-testid='lg-cloud_nav-top_nav-resource_nav-segment-button']",
            timeout=15_000,
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


def login(page: Page, evidencias_dir: Path, logs_dir: Path, max_reintentos: int = 2) -> Page:
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

    page.click("[data-testid='lg-cloud_nav-top_nav-resource_nav-segment-button']")
    page.click("a[aria-label='Interseguro']")
    page.wait_for_load_state("domcontentloaded")
    print("  ✓ Organización Interseguro seleccionada")

    print("  → Entrando al proyecto PortalSistemas...")
    page.click("a[href*='66ba761f5acbaa376da8f5b3']")
    page.wait_for_load_state("domcontentloaded")
    print("  ✓ Proyecto PortalSistemas abierto")

    print("  → Navegando a Clusters...")
    page.click("[data-testid='lg-cloud_nav-side_nav-clusters']")
    page.wait_for_load_state("domcontentloaded")
    print("  ✓ Sección Clusters abierta")

    print("  → Localizando cluster vis-data-prd...")
    cluster_row = page.locator(
        "css=[data-testid='cluster-name-detail-link'][href*='vis-data-prd']"
        " >> xpath=ancestor::div[contains(@class,'e15qq9hb5')]"
    ).first
    dropdown_btn = cluster_row.locator("[data-testid='Dropdown_toggleButton']").first
    dropdown_btn.click()
    print("  ✓ Menú del cluster abierto")

    print("  → Haciendo clic en Download Logs...")
    page.click("a.dropdown-component-link:has-text('Download Logs')")
    page.wait_for_load_state("domcontentloaded")
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
) -> list[Path]:
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
    
    Returns:
        Lista de Paths de las capturas generadas (para usar en IPE).
    """
    process_value = _PROCESS_VALUE.get(tipo_log)
    if process_value is None:
        raise ValueError(f"tipo_log inválido: {tipo_log!r}. Usa 'audit' o 'general'.")

    print(f"[4/N] Descargando {tipo_log} log ({start} → {end})...")

    # 1. Seleccionar proceso
    print(f"  → Seleccionando proceso: {process_value}...")
    page.select_option("select[name='processes']", value=process_value)

    # 2. Seleccionar servidor
    print(f"  → Seleccionando servidor: {config.LOG_SERVER}...")
    page.select_option("select[name='hostnames']", value=config.LOG_SERVER)

    # 3. Seleccionar Custom Time en Time Period
    print("  → Seleccionando Custom Time...")
    page.select_option("select[name='timePeriods']", value="Custom Time")

    # 4. Fechas: formato "Sun Feb 01 2026"
    start_str = start.strftime(_DATE_FMT)
    end_str   = end.strftime(_DATE_FMT)

    print(f"  → Ingresando fecha inicio: {start_str} 12:00am...")
    _set_date_input(page, "input[name='startDate']", start_str)
    _set_time_input(page, ".js-start-time-container", "12:00am")

    print(f"  → Ingresando fecha fin: {end_str} 11:30pm...")
    _set_date_input(page, "input[name='endDate']", end_str)
    _set_time_input(page, ".js-end-time-container", "11:30pm")

    cap1 = capturar(evidencias_dir, f"04_filtro_{tipo_log}_log", page)

    # 5. Descargar
    print("  → Haciendo clic en Download Logs...")
    with page.expect_download() as dl_info:
        page.click("button[data-testid='download-logs-modal']")

    descarga = dl_info.value
    nombre = descarga.suggested_filename
    # Obtener la carpeta Descargas real de Windows (independiente del idioma).
    # FOLDERID_Downloads GUID: {374DE290-123F-4565-9164-39C4925E467B}
    _guid = struct.pack("<IHH8s", 0x374DE290, 0x123F, 0x4565,
                        bytes([0x91, 0x64, 0x39, 0xC4, 0x92, 0x5E, 0x46, 0x7B]))
    _buf = ctypes.c_wchar_p()
    ctypes.windll.shell32.SHGetKnownFolderPath(_guid, 0, None, ctypes.byref(_buf))
    downloads_win = Path(_buf.value) if _buf.value else Path.home() / "Downloads"
    downloads_win.mkdir(parents=True, exist_ok=True)
    tmp_path = downloads_win / nombre
    descarga.save_as(str(tmp_path))
    print(f"  ✓ Descarga guardada: {tmp_path}")

    # Captura post-descarga con la notificación de Chrome visible
    time.sleep(1.5)
    cap2 = capturar(evidencias_dir, f"05_descarga_completada_{tipo_log}_log", page)

    # Captura de Propiedades mostrando la ruta de Descargas de Windows
    capturar_propiedades_archivo(evidencias_dir, tmp_path, f"06_{tipo_log}_log")
    cap3 = evidencias_dir / f"{tmp_path.stem.split('_')[0]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_06_{tipo_log}_log_propiedades_archivo.png"
    if not cap3.exists():
        # Buscar el archivo más reciente que coincida con el patrón
        capturas_props = sorted(evidencias_dir.glob(f"*_06_{tipo_log}_log_propiedades_archivo.png"))
        cap3 = capturas_props[-1] if capturas_props else cap2

    # Mover el archivo a la carpeta de resultados
    destino = evidencias_dir / nombre
    shutil.move(str(tmp_path), str(destino))
    print(f"  ✓ Archivo movido a: {destino}")
    
    return [cap1, cap2, cap3]
