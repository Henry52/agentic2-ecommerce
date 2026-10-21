"""API FastAPI del router de ecommerce.

Levantar en local:
    uvicorn api.app:app --reload --port 8000

Swagger completo en http://localhost:8000/docs
"""

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from fastapi import Body, FastAPI, HTTPException, status
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.router.graph import graph

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("api.heroku")

MODELO = os.getenv("MODELO", "gemini-3.5-flash-lite")

RUTAS_VALIDAS = ("preventa", "postventa", "generica")


class ChatRequest(BaseModel):
    """Body de entrada de /chat."""

    user_id: str = Field(
        ...,
        description="Identificador del usuario. Se usa como `thread_id` para que el router recuerde la conversación.",
        examples=["user-42"],
    )
    texto: str = Field(
        ...,
        min_length=1,
        description="Mensaje del cliente que se debe clasificar y enrutar.",
        examples=["¿tienen la polera azul en talla M?"],
    )


class ChatResponse(BaseModel):
    """Body de salida de /chat."""

    ruta: Literal["preventa", "postventa", "generica"] = Field(
        ...,
        description="Agente destino: preventa (antes de comprar), postventa (pedido ya realizado) o generica (no es del ecommerce).",
        examples=["preventa"],
    )
    motivo: str = Field(
        ...,
        description="Una frase que explica por qué se eligió esa ruta.",
        examples=["El cliente pregunta por la disponibilidad y talla de un producto antes de comprar."],
    )
    respuesta: str = Field(
        ...,
        description="Texto final que devuelve el agente destino al cliente.",
        examples=["Soy el agente de preventa. Recibí: ¿tienen la polera azul en talla M?. Pronto podré ayudarte con productos y compras."],
    )


class HealthResponse(BaseModel):
    """Body de salida de /health."""

    ok: bool = Field(..., description="True si la API está viva.", examples=[True])
    modelo: str = Field(..., description="Modelo de Google GenAI que usa el router.", examples=["gemini-3.5-flash-lite"])


class DetalleValidacion(BaseModel):
    """Un error de campo de la validación de pydantic."""

    loc: list[str] = Field(..., description="Ubicación del campo que falló.", examples=[["body", "texto"]])
    msg: str = Field(..., description="Descripción del error.", examples=["Field required"])
    type: str = Field(..., description="Tipo de error de validación.", examples=["missing"])


class ErrorValidacion(BaseModel):
    """Body de la respuesta 422."""

    detail: list[DetalleValidacion] = Field(..., description="Lista de errores de validación del body.")


class ErrorModelo(BaseModel):
    """Body de la respuesta 502."""

    detail: str = Field(
        ...,
        description="Mensaje claro para el cliente. Nunca incluye credenciales ni stack trace.",
        examples=["El modelo no respondió correctamente. Inténtalo de nuevo en unos segundos."],
    )


class TelegramResponse(BaseModel):
    """Body de salida de /telegram."""

    ok: bool = Field(..., description="True si el webhook se recibió.", examples=[True])


@asynccontextmanager
async def lifespan(app: FastAPI):
    """El grafo se compila una sola vez al importar el módulo (arranque de la app)."""
    logger.info("Router listo. modelo=%s rutas=%s", MODELO, ", ".join(RUTAS_VALIDAS))
    yield
    logger.info("API apagada.")


app = FastAPI(
    title="Ecommerce Router API",
    version="1.0.0",
    summary="Clasifica mensajes de clientes de ecommerce y los enruta a preventa, postventa o genérica.",
    description=(
        "Router de un chat de ecommerce construido con LangGraph.\n\n"
        "Recibe el mensaje de un cliente, decide a qué agente pertenece y devuelve la respuesta del agente destino.\n\n"
        "Las tres rutas posibles son:\n"
        "- **preventa**: intención de compra, preguntas por productos, precios, tallas, stock, promociones y formas de pago **antes** de comprar.\n"
        "- **postventa**: quejas, reclamos, seguimiento de un pedido **ya realizado**, devoluciones, cambios, garantía o productos dañados.\n"
        "- **generica**: saludos o cualquier mensaje ajeno al ecommerce (clima, chistes, preguntas generales).\n\n"
        "Si el modelo duda entre preventa y postventa, la clave es si el cliente **ya compró**.\n\n"
        "La memoria de la conversación se guarda por `user_id` (usado como `thread_id`)."
    ),
    lifespan=lifespan,
    openapi_tags=[
        {"name": "salud", "description": "Estado del servicio."},
        {"name": "chat", "description": "Ruteo de mensajes de clientes del ecommerce."},
        {"name": "telegram", "description": "Webhook entrante de Telegram."},
    ],
)


@app.get(
    "/health",
    tags=["salud"],
    response_model=HealthResponse,
    summary="Estado del servicio",
    description="Devuelve si la API está viva y qué modelo de Google GenAI está usando el router.",
    responses={200: {"description": "La API está viva.", "model": HealthResponse}},
)
def health() -> HealthResponse:
    return HealthResponse(ok=True, modelo=MODELO)


@app.post(
    "/chat",
    tags=["chat"],
    response_model=ChatResponse,
    summary="Rutea un mensaje de cliente",
    description=(
        "Clasifica el mensaje con el modelo y lo envía al agente destino.\n\n"
        "La conversación se recuerda por `user_id`, que se usa como `thread_id`."
    ),
    responses={
        200: {"description": "Mensaje clasificado y respondido por el agente destino.", "model": ChatResponse},
        422: {
            "description": "Body inválido: falta `user_id`, falta `texto` o `texto` viene vacío.",
            "model": ErrorValidacion,
        },
        502: {
            "description": "El modelo de Google GenAI falló o devolvió una ruta no válida.",
            "model": ErrorModelo,
        },
    },
)
def chat(pedido: ChatRequest) -> ChatResponse:
    try:
        resultado = graph.invoke(
            {"mensaje": pedido.texto},
            config={"configurable": {"thread_id": pedido.user_id}},
        )
    except Exception:
        logger.exception("Fallo el modelo al rutear el mensaje de user_id=%s", pedido.user_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="El modelo no respondió correctamente. Inténtalo de nuevo en unos segundos.",
        ) from None

    if not isinstance(resultado, dict):
        logger.error("El grafo devolvió un resultado inesperado: %r", type(resultado))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="El modelo no respondió correctamente. Inténtalo de nuevo en unos segundos.",
        )

    ruta = resultado.get("ruta")
    if ruta not in RUTAS_VALIDAS:
        logger.error("El grafo devolvió una ruta inválida: %r", ruta)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="El modelo no respondió correctamente. Inténtalo de nuevo en unos segundos.",
        )

    return ChatResponse(
        ruta=ruta,
        motivo=str(resultado.get("motivo", "")),
        respuesta=str(resultado.get("respuesta", "")),
    )


@app.post(
    "/telegram",
    tags=["telegram"],
    response_model=TelegramResponse,
    include_in_schema=False,
    summary="Webhook entrante de Telegram",
    description="Recibe las actualizaciones del webhook de Telegram. Se completa en la parte 5.",
)
async def telegram(payload: Any = Body(...)) -> TelegramResponse:
    logger.info("Actualización de Telegram recibida. tipo=%s", type(payload).__name__)
    return TelegramResponse(ok=True)
