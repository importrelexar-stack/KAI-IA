"""Servidor MCP mínimo para las pruebas de integración (stdio)."""

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

mcp = FastMCP("demo")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def sumar(a: int, b: int) -> str:
    """Suma dos números."""
    return f"Resultado: {a + b}"


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def clave_configurada() -> str:
    """Indica si la variable secreta llegó al servidor (sin revelarla)."""
    return "clave ok" if os.environ.get("DEMO_KEY") == "s3cr3t" else "sin clave"


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False))
def crear_nota(texto: str) -> str:
    """Agrega una nota al archivo de notas."""
    path = Path(os.environ["NOTES_FILE"])
    with path.open("a", encoding="utf-8") as f:
        f.write(texto + "\n")
    return "Nota guardada"


if __name__ == "__main__":
    mcp.run()
