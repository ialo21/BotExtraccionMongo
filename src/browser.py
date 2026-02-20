"""
Gestión del ciclo de vida del navegador (Playwright).
Incluye configuración anti-detección para evitar bloqueos por bot-detection.
"""
import random
from playwright.sync_api import sync_playwright, Browser, Page
import config


_playwright = None
_browser: Browser | None = None

# ── Argumentos de Chromium para reducir fingerprint de automatización ──────────
_ANTI_BOT_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
    "--no-first-run",
    "--no-service-autorun",
    "--password-store=basic",
    "--use-mock-keychain",
    "--disable-background-networking",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-breakpad",
    "--disable-client-side-phishing-detection",
    "--disable-default-apps",
    "--disable-domain-reliability",
    "--disable-hang-monitor",
    "--disable-ipc-flooding-protection",
    "--disable-prompt-on-repost",
    "--disable-renderer-backgrounding",
    "--disable-sync",
    "--disable-translate",
    "--metrics-recording-only",
    "--safebrowsing-disable-auto-update",
    "--start-maximized",
]

# ── Pool de User-Agents reales (Chrome 132 / Windows 10) ──────────────────────
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
]

# ── Script inyectado en cada frame antes de que cargue la página ──────────────
# Oculta todos los indicadores estándar de WebDriver / CDP automation.
_STEALTH_INIT_SCRIPT = """() => {
    // Ocultar propiedad webdriver
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
        configurable: true
    });

    // Simular plugins como en Chrome real
    Object.defineProperty(navigator, 'plugins', {
        get: () => {
            const arr = [1, 2, 3, 4, 5];
            arr.__proto__ = PluginArray.prototype;
            return arr;
        },
        configurable: true
    });

    // Idiomas coherentes con Perú
    Object.defineProperty(navigator, 'languages', {
        get: () => ['es-PE', 'es', 'en-US', 'en'],
        configurable: true
    });

    // Plataforma
    Object.defineProperty(navigator, 'platform', {
        get: () => 'Win32',
        configurable: true
    });

    // chrome.runtime presente en Chrome real, ausente en bots
    if (!window.chrome) {
        window.chrome = {
            runtime: {},
            loadTimes: () => {},
            csi: () => {},
            app: {}
        };
    }

    // Permisos: devolver estado real en vez de delatar automation
    const _origQuery = window.navigator.permissions.query.bind(navigator.permissions);
    window.navigator.permissions.query = (params) =>
        params.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : _origQuery(params);

    // Eliminar variables de CDP que detectan Selenium/Playwright
    const _cdpVars = [
        'cdc_adoQpoasnfa76pfcZLmcfl_Array',
        'cdc_adoQpoasnfa76pfcZLmcfl_Promise',
        'cdc_adoQpoasnfa76pfcZLmcfl_Symbol',
        '__playwright',
        '__pw_manual',
    ];
    _cdpVars.forEach(v => { try { delete window[v]; } catch (_) {} });
}"""


def launch() -> Page:
    """
    Inicia el navegador con configuración anti-detección y devuelve la página activa.
    Cada ejecución rota el User-Agent para reducir patrones reconocibles.
    """
    global _playwright, _browser

    config.DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    _playwright = sync_playwright().start()
    _browser = _playwright.chromium.launch(
        headless=config.HEADLESS,
        downloads_path=str(config.DOWNLOAD_DIR),
        args=_ANTI_BOT_ARGS,
    )

    user_agent = random.choice(_USER_AGENTS)
    print(f"  [browser] User-Agent: {user_agent[:60]}...")

    context = _browser.new_context(
        accept_downloads=True,
        no_viewport=True,
        user_agent=user_agent,
        locale="es-PE",
        timezone_id="America/Lima",
        extra_http_headers={
            "Accept-Language": "es-PE,es;q=0.9,en-US;q=0.8,en;q=0.7",
        },
    )

    # Inyectar stealth antes de que cualquier script de la página se ejecute
    context.add_init_script(_STEALTH_INIT_SCRIPT)

    page = context.new_page()
    page.set_default_timeout(config.PAGE_TIMEOUT)
    return page


def close():
    """Cierra el navegador y libera recursos."""
    global _playwright, _browser
    if _browser:
        _browser.close()
    if _playwright:
        _playwright.stop()
    _browser = None
    _playwright = None
