"""Registra el webhook de Telegram con la URL pública configurada en .env."""

import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def main() -> int:
    load_dotenv(ENV_PATH)
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    secret = os.getenv("TELEGRAM_SECRET", "")
    public_url = os.getenv("PUBLIC_URL", "").strip().rstrip("/")
    missing = [
        name
        for name, value in (
            ("TELEGRAM_TOKEN", token),
            ("TELEGRAM_SECRET", secret),
            ("PUBLIC_URL", public_url),
        )
        if not value
    ]
    if missing:
        print(f"Faltan variables de entorno: {', '.join(missing)}", file=sys.stderr)
        return 1

    if not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", secret):
        print("TELEGRAM_SECRET debe tener 1–256 caracteres: letras, números, _ o -.", file=sys.stderr)
        return 1

    try:
        url = urlsplit(public_url)
        valid_url = (
            url.scheme == "https"
            and url.hostname
            and not url.username
            and not url.password
            and not url.query
            and not url.fragment
        )
    except ValueError:
        valid_url = False
    if not valid_url:
        print("PUBLIC_URL debe ser una URL https pública, sin credenciales, query ni fragmento.", file=sys.stderr)
        return 1

    try:
        response = httpx.post(
            f"https://api.telegram.org/bot{token}/setWebhook",
            json={"url": f"{public_url}/telegram", "secret_token": secret},
            timeout=10.0,
        )
    except httpx.HTTPError as error:
        # La URL de las excepciones HTTP contiene el token del bot.
        print(f"No se pudo contactar con Telegram ({type(error).__name__}).", file=sys.stderr)
        return 1

    try:
        result = response.json()
    except ValueError:
        print(f"Telegram devolvió una respuesta no JSON (HTTP {response.status_code}).", file=sys.stderr)
        return 1

    output = json.dumps(result, ensure_ascii=False, indent=2)
    print(output.replace(token, "[TOKEN OCULTO]").replace(secret, "[SECRETO OCULTO]"))
    return 0 if response.is_success and isinstance(result, dict) and result.get("ok") is True else 1


if __name__ == "__main__":
    sys.exit(main())
