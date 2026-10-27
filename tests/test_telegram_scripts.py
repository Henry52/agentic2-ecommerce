"""Pruebas de los comandos de Telegram sin llamadas de red ni credenciales reales."""

import json

import httpx
import pytest

from scripts import set_webhook, webhook_info


@pytest.fixture(autouse=True)
def telegram_env(monkeypatch, tmp_path):
    for module in (set_webhook, webhook_info):
        monkeypatch.setattr(module, "ENV_PATH", tmp_path / ".env")
    monkeypatch.setenv("TELEGRAM_TOKEN", "123:token-de-prueba")
    monkeypatch.setenv("TELEGRAM_SECRET", "secreto_de_prueba")
    monkeypatch.setenv("PUBLIC_URL", "https://tienda.example/")


def test_set_webhook_registra_url_y_secreto(monkeypatch, capsys):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(200, json={"ok": True, "result": True})

    monkeypatch.setattr(httpx, "post", post)
    assert set_webhook.main() == 0
    assert calls == [
        (
            "https://api.telegram.org/bot123:token-de-prueba/setWebhook",
            {
                "json": {
                    "url": "https://tienda.example/telegram",
                    "secret_token": "secreto_de_prueba",
                },
                "timeout": 10.0,
            },
        )
    ]
    assert json.loads(capsys.readouterr().out) == {"ok": True, "result": True}


def test_webhook_info_muestra_estado_y_errores(monkeypatch, capsys):
    result = {
        "ok": True,
        "result": {
            "url": "https://tienda.example/telegram",
            "pending_update_count": 3,
            "last_error_message": "Wrong response from the webhook: 403 Forbidden",
        },
    }

    def post(url, **kwargs):
        assert url == "https://api.telegram.org/bot123:token-de-prueba/getWebhookInfo"
        assert kwargs["timeout"] > 0
        return httpx.Response(200, json=result)

    monkeypatch.setattr(httpx, "post", post)
    assert webhook_info.main() == 0
    assert json.loads(capsys.readouterr().out) == result


@pytest.mark.parametrize("name", ["TELEGRAM_TOKEN", "TELEGRAM_SECRET", "PUBLIC_URL"])
def test_set_webhook_rechaza_configuracion_incompleta(name, monkeypatch, capsys):
    monkeypatch.delenv(name)
    monkeypatch.setattr(httpx, "post", lambda *a, **k: pytest.fail("No debe llamar a Telegram"))
    assert set_webhook.main() == 1
    assert name in capsys.readouterr().err


@pytest.mark.parametrize("url", ["http://tienda.example", "https://", "https://tienda.example?x=1"])
def test_set_webhook_rechaza_url_invalida(url, monkeypatch):
    monkeypatch.setenv("PUBLIC_URL", url)
    monkeypatch.setattr(httpx, "post", lambda *a, **k: pytest.fail("No debe llamar a Telegram"))
    assert set_webhook.main() == 1


@pytest.mark.parametrize("secret", ["tiene espacios", "á", "a" * 257])
def test_set_webhook_rechaza_secreto_invalido(secret, monkeypatch):
    monkeypatch.setenv("TELEGRAM_SECRET", secret)
    monkeypatch.setattr(httpx, "post", lambda *a, **k: pytest.fail("No debe llamar a Telegram"))
    assert set_webhook.main() == 1


def test_webhook_info_requiere_token(monkeypatch):
    monkeypatch.delenv("TELEGRAM_TOKEN")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: pytest.fail("No debe llamar a Telegram"))
    assert webhook_info.main() == 1


@pytest.mark.parametrize("module", [set_webhook, webhook_info])
def test_error_http_devuelve_fallo_sin_exponer_token(module, monkeypatch, capsys):
    def post(url, **kwargs):
        raise httpx.ConnectError(f"Error conectando a {url}")

    monkeypatch.setattr(httpx, "post", post)
    assert module.main() == 1
    output = capsys.readouterr()
    assert "ConnectError" in output.err
    assert "token-de-prueba" not in output.err + output.out


@pytest.mark.parametrize("module", [set_webhook, webhook_info])
def test_error_de_telegram_se_imprime_y_devuelve_fallo(module, monkeypatch, capsys):
    result = {"ok": False, "error_code": 401, "description": "Unauthorized"}
    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(401, json=result))
    assert module.main() == 1
    assert json.loads(capsys.readouterr().out) == result


@pytest.mark.parametrize("module", [set_webhook, webhook_info])
def test_respuesta_no_json_devuelve_fallo(module, monkeypatch, capsys):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(502, text="Bad gateway"))
    assert module.main() == 1
    assert "no JSON" in capsys.readouterr().err


def test_dotenv_carga_faltantes_sin_sobrescribir_entorno(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text(
        "TELEGRAM_TOKEN=999:token-del-archivo\n"
        "TELEGRAM_SECRET=secreto_del_archivo\n"
        "PUBLIC_URL=https://archivo.example\n"
    )
    monkeypatch.delenv("TELEGRAM_SECRET")
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs["json"]))
        return httpx.Response(200, json={"ok": True, "result": True})

    monkeypatch.setattr(httpx, "post", post)
    assert set_webhook.main() == 0
    assert calls[0] == (
        "https://api.telegram.org/bot123:token-de-prueba/setWebhook",
        {"url": "https://tienda.example/telegram", "secret_token": "secreto_del_archivo"},
    )
