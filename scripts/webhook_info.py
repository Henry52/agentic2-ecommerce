"""Muestra la configuración del webhook y los errores pendientes de Telegram."""

import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def main() -> int:
    load_dotenv(ENV_PATH)
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    if not token:
        print("Falta la variable de entorno TELEGRAM_TOKEN.", file=sys.stderr)
        return 1

    try:
        response = httpx.post(
            f"https://api.telegram.org/bot{token}/getWebhookInfo",
            timeout=10.0,
        )
    except httpx.HTTPError as error:
        # No imprimir la URL: incluye el token del bot.
        print(f"No se pudo contactar con Telegram ({type(error).__name__}).", file=sys.stderr)
        return 1

    try:
        result = response.json()
    except ValueError:
        print(f"Telegram devolvió una respuesta no JSON (HTTP {response.status_code}).", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2).replace(token, "[TOKEN OCULTO]"))
    return 0 if response.is_success and isinstance(result, dict) and result.get("ok") is True else 1


if __name__ == "__main__":
    sys.exit(main())
