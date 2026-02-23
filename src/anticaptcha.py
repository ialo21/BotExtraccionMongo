"""
Integración con Anti-Captcha para resolver reCAPTCHA Enterprise v3.

MongoDB Atlas usa reCAPTCHA Enterprise servido desde www.recaptcha.net.
La librería anticaptchaofficial no incluye isEnterprise/apiDomain en su
payload por defecto, por eso se subclasifica y se sobreescribe solve_and_return_solution.
"""
import time

from anticaptchaofficial.recaptchav3proxyless import recaptchaV3Proxyless

import config


class _RecaptchaV3Enterprise(recaptchaV3Proxyless):
    """
    Extiende recaptchaV3Proxyless añadiendo soporte para reCAPTCHA Enterprise
    y el dominio de API www.recaptcha.net que usa MongoDB Atlas.
    """

    api_domain: str = "www.recaptcha.net"

    def solve_and_return_solution(self):
        task_payload = {
            "clientKey": self.client_key,
            "task": {
                "type": "RecaptchaV3TaskProxyless",
                "websiteURL": self.website_url,
                "websiteKey": self.website_key,
                "minScore": self.min_score,
                "pageAction": self.page_action,
                "isEnterprise": True,
                "apiDomain": self.api_domain,
            },
            "softId": self.soft_id,
        }

        if self.create_task(task_payload) == 1:
            self.log("created task with id " + str(self.task_id))
        else:
            self.log("could not create task")
            self.log(self.err_string)
            return 0

        time.sleep(3)
        task_result = self.wait_for_result(60)
        if task_result == 0:
            return 0
        return task_result["solution"]["gRecaptchaResponse"]


def resolver_recaptcha_v3(page_url: str, site_key: str, action: str = "login") -> str:
    """
    Resuelve un reCAPTCHA Enterprise v3 usando Anti-Captcha.

    Args:
        page_url:  URL de la página donde vive el captcha.
        site_key:  Clave pública del sitio (parámetro k= del iframe).
        action:    Valor de pageAction configurado por el sitio.

    Returns:
        Token g-recaptcha-response listo para inyectar en el formulario.

    Raises:
        RuntimeError: si Anti-Captcha no pudo resolver el captcha.
    """
    solver = _RecaptchaV3Enterprise()
    solver.set_verbose(1)
    solver.set_key(config.ANTICAPTCHA_API_KEY)
    solver.set_website_url(page_url)
    solver.set_website_key(site_key)
    solver.set_page_action(action)
    # 0.7 equilibra disponibilidad de workers y calidad de puntuación
    solver.set_min_score(0.7)

    token = solver.solve_and_return_solution()
    if token == 0:
        raise RuntimeError(
            f"Anti-Captcha no pudo resolver reCAPTCHA Enterprise: {solver.error_code}"
        )

    return token
