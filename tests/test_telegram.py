"""Contrato del webhook de Telegram, sin llamadas reales al modelo ni a Telegram."""

import asyncio
import json
import logging
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient

import api.app as modulo


ASYNC_CLIENT = httpx.AsyncClient
TOKEN = "123456:token_solo_para_pruebas"
SECRET = "secreto_solo_para_pruebas"
HEADERS = {"X-Telegram-Bot-Api-Secret-Token": SECRET}
RESULTADO = {"ruta": "preventa", "motivo": "Consulta antes de comprar", "respuesta": "Tenemos talla M."}


def update(chat_id=123, texto="¿Tienen talla M?"):
    return {"update_id": 1, "message": {"chat": {"id": chat_id}, "text": texto}}


@pytest.fixture
def telegram(monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", TOKEN)
    monkeypatch.setenv("TELEGRAM_SECRET", SECRET)
    grafo = Mock(return_value=dict(RESULTADO))
    monkeypatch.setattr(modulo.graph, "invoke", grafo)
    envio = Mock(return_value=httpx.Response(200, json={"ok": True, "result": {"message_id": 1}}))
    solicitudes = []

    def transportar(request):
        solicitudes.append(request)
        return envio(request)

    def cliente(**kwargs):
        return ASYNC_CLIENT(transport=httpx.MockTransport(transportar), **kwargs)

    monkeypatch.setattr(modulo.httpx, "AsyncClient", cliente)
    return SimpleNamespace(
        client=TestClient(modulo.app), grafo=grafo, envio=envio, solicitudes=solicitudes
    )


def test_telegram_envia_respuesta_y_registra_ruta(telegram, caplog):
    caplog.set_level(logging.INFO, logger="api.heroku")
    r = telegram.client.post("/telegram", json=update(-1001234567890), headers=HEADERS)

    assert r.status_code == 200
    assert r.json() == {"ok": True}
    telegram.grafo.assert_called_once_with(
        {"mensaje": "¿Tienen talla M?"},
        config={"configurable": {"thread_id": "-1001234567890"}},
    )
    assert len(telegram.solicitudes) == 1
    enviada = telegram.solicitudes[0]
    assert enviada.method == "POST"
    assert str(enviada.url) == f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    assert json.loads(enviada.content) == {"chat_id": -1001234567890, "text": RESULTADO["respuesta"]}
    assert "chat_id=-1001234567890" in caplog.text
    assert "ruta=preventa" in caplog.text
    assert RESULTADO["motivo"] in caplog.text
    assert TOKEN not in caplog.text
    assert SECRET not in caplog.text


def test_telegram_reutiliza_thread_por_chat_y_separa_chats(telegram):
    for chat_id in (123, 123, 456):
        r = telegram.client.post("/telegram", json=update(chat_id), headers=HEADERS)
        assert r.status_code == 200

    assert [c.kwargs["config"]["configurable"]["thread_id"] for c in telegram.grafo.call_args_list] == [
        "123", "123", "456"
    ]


def test_telegram_divide_respuestas_largas_sin_perder_texto(telegram):
    respuesta = "a" * 4096 + "fin de la respuesta"
    telegram.grafo.return_value = {**RESULTADO, "respuesta": respuesta}
    r = telegram.client.post("/telegram", json=update(), headers=HEADERS)

    assert r.status_code == 200
    mensajes = [json.loads(solicitud.content) for solicitud in telegram.solicitudes]
    assert len(mensajes) == 2
    assert all(mensaje["chat_id"] == 123 and len(mensaje["text"]) <= 4096 for mensaje in mensajes)
    assert "".join(mensaje["text"] for mensaje in mensajes) == respuesta


@pytest.mark.parametrize("headers", [{}, {"X-Telegram-Bot-Api-Secret-Token": "incorrecto"}])
def test_telegram_rechaza_secreto_antes_de_procesar(telegram, headers):
    r = telegram.client.post("/telegram", content="json inválido", headers=headers)
    assert r.status_code == 403
    telegram.grafo.assert_not_called()
    telegram.envio.assert_not_called()


@pytest.mark.parametrize("secret", [None, ""])
def test_telegram_no_admite_secreto_sin_configurar(telegram, monkeypatch, secret):
    if secret is None:
        monkeypatch.delenv("TELEGRAM_SECRET")
    else:
        monkeypatch.setenv("TELEGRAM_SECRET", secret)
    r = telegram.client.post("/telegram", json=update(), headers={"X-Telegram-Bot-Api-Secret-Token": ""})
    assert r.status_code == 403
    telegram.grafo.assert_not_called()
    telegram.envio.assert_not_called()


@pytest.mark.parametrize(
    "payload",
    [
        {},
        [],
        {"callback_query": {"data": "opción"}},
        {"message": None},
        {"message": {"chat": {"id": 123}, "photo": [{}]}},
        {"message": {"chat": {"id": 123}, "caption": "Foto"}},
        {"message": {"text": "hola"}},
        update(texto=""),
        update(texto=123),
        update(chat_id=True),
        update(chat_id="123"),
    ],
)
def test_telegram_ignora_updates_sin_mensaje_util(telegram, payload):
    r = telegram.client.post("/telegram", json=payload, headers=HEADERS)
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    telegram.grafo.assert_not_called()
    telegram.envio.assert_not_called()


def test_telegram_ignora_json_invalido(telegram):
    r = telegram.client.post("/telegram", content="{", headers=HEADERS)
    assert r.status_code == 200
    telegram.grafo.assert_not_called()
    telegram.envio.assert_not_called()


def test_telegram_confirma_200_si_falla_modelo_sin_exponer_secreto(telegram, caplog):
    telegram.grafo.side_effect = RuntimeError(f"Credenciales inválidas: {TOKEN} {SECRET}")
    r = telegram.client.post("/telegram", json=update(), headers=HEADERS)
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    telegram.envio.assert_not_called()
    assert caplog.records
    assert TOKEN not in caplog.text + r.text
    assert SECRET not in caplog.text + r.text


@pytest.mark.parametrize(
    "resultado",
    [None, {"ruta": "desconocida", "respuesta": "hola"}, {"ruta": "preventa", "respuesta": ""}],
)
def test_telegram_no_envia_resultados_invalidos_del_grafo(telegram, resultado):
    telegram.grafo.return_value = resultado
    r = telegram.client.post("/telegram", json=update(), headers=HEADERS)
    assert r.status_code == 200
    telegram.envio.assert_not_called()


@pytest.mark.parametrize("fallo", ["http", "timeout", "ok_false", "json_invalido"])
def test_telegram_confirma_200_si_falla_envio(telegram, caplog, fallo):
    if fallo == "http":
        telegram.envio.return_value = httpx.Response(401, json={"ok": False, "description": "Unauthorized"})
    elif fallo == "timeout":
        telegram.envio.side_effect = httpx.ReadTimeout(f"Timeout https://api.telegram.org/bot{TOKEN}/sendMessage")
    elif fallo == "ok_false":
        telegram.envio.return_value = httpx.Response(200, json={"ok": False, "description": "Error"})
    else:
        telegram.envio.return_value = httpx.Response(200, text="no es JSON")

    r = telegram.client.post("/telegram", json=update(), headers=HEADERS)
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    telegram.envio.assert_called_once()
    assert any(record.levelno >= logging.ERROR for record in caplog.records)
    assert TOKEN not in caplog.text + r.text


def test_telegram_confirma_200_sin_token(telegram, monkeypatch):
    monkeypatch.delenv("TELEGRAM_TOKEN")
    r = telegram.client.post("/telegram", json=update(), headers=HEADERS)
    assert r.status_code == 200
    telegram.envio.assert_not_called()


def test_telegram_ejecuta_modelo_fuera_del_bucle_async(telegram):
    def invocar(*args, **kwargs):
        with pytest.raises(RuntimeError, match="no running event loop"):
            asyncio.get_running_loop()
        return RESULTADO

    telegram.grafo.side_effect = invocar
    r = telegram.client.post("/telegram", json=update(), headers=HEADERS)
    assert r.status_code == 200
    telegram.envio.assert_called_once()


def test_telegram_espera_el_envio_antes_de_confirmar(telegram, monkeypatch):
    async def escenario():
        enviando = asyncio.Event()
        permitir_envio = asyncio.Event()

        async def transportar(request):
            enviando.set()
            await permitir_envio.wait()
            return httpx.Response(200, json={"ok": True})

        monkeypatch.setattr(
            modulo.httpx,
            "AsyncClient",
            lambda **kwargs: ASYNC_CLIENT(transport=httpx.MockTransport(transportar), **kwargs),
        )
        async with ASYNC_CLIENT(transport=httpx.ASGITransport(app=modulo.app), base_url="http://test") as client:
            tarea = asyncio.create_task(client.post("/telegram", json=update(), headers=HEADERS))
            try:
                await asyncio.wait_for(enviando.wait(), timeout=2)
                assert not tarea.done()
            finally:
                permitir_envio.set()
            r = await asyncio.wait_for(tarea, timeout=2)
            assert r.status_code == 200
            assert r.json() == {"ok": True}

    asyncio.run(escenario())
