"""
Gestión del ciclo de vida del navegador (Playwright).
"""
from playwright.sync_api import sync_playwright, Browser, Page
import config


_playwright = None
_browser: Browser | None = None


def launch() -> Page:
    """Inicia el navegador y devuelve la página activa."""
    global _playwright, _browser

    # Garantizar que el directorio de descargas existe antes de pasárselo a Playwright.
    # DOWNLOAD_DIR ya es absoluto (resuelto en config.py), así no depende del cwd.
    config.DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    _playwright = sync_playwright().start()
    _browser = _playwright.chromium.launch(
        headless=config.HEADLESS,
        downloads_path=str(config.DOWNLOAD_DIR),
        args=["--start-maximized"],
    )
    context = _browser.new_context(
        accept_downloads=True,
        no_viewport=True,
    )
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
