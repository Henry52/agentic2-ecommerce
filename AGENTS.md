# AGENTS.md — Reglas del proyecto

## 1. Estructura de agentes
- Los agentes van en `src/{nombre_agente}/` con exactamente estos 3 archivos:
  - `graph.py`: define y compila el grafo LangGraph. Expone `graph`. Nada de reglas/prompts hardcodeados aquí.
  - `prompts.py`: cada nodo con su propio prompt. Toda regla de comportamiento vive aquí, nunca en `graph.py`.
  - `tools.py`: herramientas del agente (funciones/tool calls).
- `graph.py` solo orquesta: nodos, aristas, estado. Importa prompts y tools.

## 2. Ejecución desde raíz
- Se ejecutan desde la raíz:
  ```
  python main.py {nombre_agente} "mensaje"
  ```
- Flag `--saltos`: imprime los nodos por los que pasó el grafo.
- Flag `--diagrama`: imprime el Mermaid del grafo sin ejecutarlo.
- Flag `--thread {id}`: `thread_id` de la memoria (por defecto `default`).
- Ejemplo:
  ```
  python main.py mi_agente "hola" --saltos
  python main.py mi_agente "hola" --diagrama
  ```

## 3. API
- La API va en `api/app.py` (FastAPI) y se levanta con:
  ```
  uvicorn api.app:app --reload --port 8000
  ```

## 4. Scripts y pruebas
- Los scripts sueltos van en `scripts/`.
- Las pruebas van en `tests/` y se ejecutan con `pytest`.

## 5. Heroku / despliegue
- `Procfile`:
  ```
  web: uvicorn api.app:app --host 0.0.0.0 --port $PORT
  ```
- Archivo `.python-version` con:
  ```
  3.12
  ```
- `requirements.txt` siempre actualizado tras instalar/actualizar dependencias:
  ```
  .venv/bin/pip freeze > requirements.txt
  ```

## 6. Ignorados / entorno
- `.gitignore` debe incluir: `.env`, `.venv`, `__pycache__` y `.langgraph_api`.
- Nunca valores reales en el código. Usar `.env` local + variables de entorno en Heroku.
- Variables esperadas (ver `.env.example`):
  - `GOOGLE_API_KEY`
  - `MODELO=gemini-3.5-flash-lite`
  - `TELEGRAM_TOKEN` (lo da BotFather; vacío hasta el paso 5)
  - `TELEGRAM_SECRET=cambiame` (secreto que Telegram manda en cada webhook para que la API lo verifique)
  - `PUBLIC_URL` (la URL https pública; vacío hasta Heroku)

## 7. Convenciones Python
- Python 3.12, entorno virtual en `.venv` (`python3.12 -m venv .venv`).
- Dependencias base: `langgraph`, `langchain`, `langchain-google-genai`, `fastapi`, `uvicorn`, `httpx`, `pydantic`, `python-dotenv`, `pytest`.

## 8. Agentes existentes
- `src/router/`: router del chat de ecommerce.
  - Estado: `mensaje`, `ruta`, `motivo`, `respuesta`, `messages` (memoria por `thread_id` con `MemorySaver`).
  - Nodo `router`: usa `MODELO` con `with_structured_output(Decision)`; `Decision.ruta` ∈ {`preventa`, `postventa`, `generica`}.
  - Arista condicional desde `router` según `ruta` hacia `agente_preventa`, `agente_postventa` o `respuesta_generica`.
  - `agente_preventa`, `agente_postventa` y `respuesta_generica` son cascarones: responden con texto fijo, sin modelo.
  - Reglas de ruteo (preventa vs postventa): si duda, la clave es si el cliente YA compró.
  - Prueba de referencia: `python scripts/probar_router.py`.
