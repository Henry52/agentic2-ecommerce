"""Herramientas del agente router. Cascarones listos para Implementar."""

from typing import Any


def buscar_producto(termino: str) -> dict[str, Any]:
    """Busca productos del catálogo por término (productos, tallas, stock, precios)."""
    return {
        "termino": termino,
        "resultados": [],
        "disponible": False,
        "nota": "Catálogo no conectado todavía.",
    }


def consultar_pedido(numero_pedido: str) -> dict[str, Any]:
    """Consulta el estado de un pedido existente (seguimiento, envío, entrega)."""
    return {
        "numero_pedido": numero_pedido,
        "estado": "desconocido",
        "nota": "Sistema de pedidos no conectado todavía.",
    }


def politica_devoluciones() -> dict[str, Any]:
    """Devuelve la política de devoluciones, cambios y garantía."""
    return {
        "devoluciones": "no_connectada",
        "cambio": "no_connectada",
        "garantia": "no_connectada",
    }


def formas_de_pago() -> list[str]:
    """Formas de pago aceptadas en preventa."""
    return []
