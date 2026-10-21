"""Prueba manual de los 6 mensajes de referencia del agente router."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.router.graph import graph

MENSAJES = [
    "¿tienen la polera azul en talla M?",
    "mi pedido 4521 llegó roto",
    "hola",
    "¿cuánto cuesta el envío a Valparaíso?",
    "quiero devolver unas zapatillas",
    "¿qué hora es en Tokio?",
]


def main() -> None:
    for i, mensaje in enumerate(MENSAJES, start=1):
        config = {"configurable": {"thread_id": f"prueba-{i}"}}
        resultado = graph.invoke({"mensaje": mensaje}, config=config)
        print(f"[{i}] {mensaje}")
        print(f"    ruta     : {resultado.get('ruta')}")
        print(f"    motivo   : {resultado.get('motivo')}")
        print(f"    respuesta: {resultado.get('respuesta')}")
        print(f"    saltos   : {' → '.join(resultado.get('saltos', []))}")
        print()


if __name__ == "__main__":
    main()
