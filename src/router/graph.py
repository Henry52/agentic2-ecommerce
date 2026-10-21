"""Grafo LangGraph del agente router. Solo orquesta: nodos, aristas y estado."""

import os
from typing import Annotated, Any, Literal, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from .prompts import (
    PROMPT_AGENTE_POSTVENTA,
    PROMPT_AGENTE_PREVENTA,
    PROMPT_RESPUESTA_GENERICA,
    PROMPT_ROUTER,
)

load_dotenv()

MODELO = os.getenv("MODELO", "gemini-3.5-flash-lite")


class Decision(BaseModel):
    ruta: Literal["preventa", "postventa", "generica"] = Field(description="A qué agente va el mensaje.")
    motivo: str = Field(description="Una frase: por qué esa ruta.")


def _mergear_saltos(acumulado: list[str], nuevo: list[str]) -> list[str]:
    """Acumula los nodos visitados; 'router' reinicia la cuenta en cada turno."""
    if not nuevo:
        return acumulado
    if nuevo[0] == "router":
        return list(nuevo)
    return acumulado + nuevo


class EstadoRouter(TypedDict, total=False):
    mensaje: str
    ruta: str
    motivo: str
    respuesta: str
    messages: Annotated[list[AnyMessage], lambda acc, upd: acc + upd]
    saltos: Annotated[list[str], _mergear_saltos]


def obtener_llm() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(model=MODELO, temperature=0)


def nodo_router(estado: EstadoRouter) -> dict[str, Any]:
    llm = ChatGoogleGenerativeAI(model=MODELO, temperature=0)
    chain = llm.with_structured_output(Decision)

    historial = list(estado.get("messages", []))
    mensaje_actual = HumanMessage(content=estado.get("mensaje", ""))
    historial.append(mensaje_actual)

    prompt = ChatPromptTemplate.from_messages(
        [("system", PROMPT_ROUTER), MessagesPlaceholder(variable_name="historial")]
    )
    decision: Decision = chain.invoke(prompt.invoke({"historial": historial}))

    return {
        "ruta": decision.ruta,
        "motivo": decision.motivo,
        "messages": [mensaje_actual, AIMessage(content=decision.motivo)],
        "saltos": ["router"],
    }


def nodo_agente_preventa(estado: EstadoRouter) -> dict[str, Any]:
    respuesta = (
        f"Soy el agente de preventa. Recibí: {estado.get('mensaje', '')}. "
        "Pronto podré ayudarte con productos y compras."
    )
    return {"respuesta": respuesta, "messages": [AIMessage(content=respuesta)], "saltos": ["agente_preventa"]}


def nodo_agente_postventa(estado: EstadoRouter) -> dict[str, Any]:
    respuesta = (
        f"Soy el agente de postventa. Recibí: {estado.get('mensaje', '')}. "
        "Pronto podré ayudarte con tu pedido."
    )
    return {"respuesta": respuesta, "messages": [AIMessage(content=respuesta)], "saltos": ["agente_postventa"]}


def nodo_respuesta_generica(estado: EstadoRouter) -> dict[str, Any]:
    respuesta = (
        "¡Hola! Este chat es para la tienda: puedo ayudarte con compras, "
        "productos y pedidos. ¿En qué te echo una mano?"
    )
    return {"respuesta": respuesta, "messages": [AIMessage(content=respuesta)], "saltos": ["respuesta_generica"]}


def enrutar(estado: EstadoRouter) -> str:
    return estado.get("ruta", "generica")


def construir_graph():
    builder = StateGraph(EstadoRouter)

    builder.add_node("router", nodo_router)
    builder.add_node("agente_preventa", nodo_agente_preventa)
    builder.add_node("agente_postventa", nodo_agente_postventa)
    builder.add_node("respuesta_generica", nodo_respuesta_generica)

    builder.add_edge(START, "router")
    builder.add_conditional_edges(
        "router",
        enrutar,
        {
            "preventa": "agente_preventa",
            "postventa": "agente_postventa",
            "generica": "respuesta_generica",
        },
    )
    builder.add_edge("agente_preventa", END)
    builder.add_edge("agente_postventa", END)
    builder.add_edge("respuesta_generica", END)

    return builder.compile(checkpointer=MemorySaver())


graph = construir_graph()
