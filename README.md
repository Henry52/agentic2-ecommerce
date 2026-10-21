# Ecommerce Router API

Router de un chat de ecommerce construido con **LangGraph** y **FastAPI**.

El router recibe el mensaje de un cliente, lo clasifica con Google Gemini y lo deriva a
uno de tres agentes. Hoy los agentes destino son cascarones, pero el enrutado ya es real.

## Qué hace el proyecto

- **Clasifica** cada mensaje del cliente con salida estructurada (`with_structured_output`).
- **Enruta** a uno de tres destinos:

  | Ruta | Cuándo entra |
  |---|---|
  | `preventa` | Intención de compra, precios, tallas, stock, promociones, formas de pago **antes** de comprar. |
  | `postventa` | Quejas, reclamos, seguimiento de un pedido **ya realizado**, devoluciones, cambios, garantía, producto dañado. |
  | `generica` | Saludos o mensajes ajenos al ecommerce (clima, chistes, preguntas generales). |

  Si el modelo duda entre `preventa` y `postventa`, la clave es si el cliente **ya compró**.
- **Recuerda** la conversación por `user_id` (usado como `thread_id` con `MemorySaver`).
- **Expone** una API REST con Swagger en `/docs` y una colección de Bruno.

## Estructura

```
api/app.py              API FastAPI (health, chat, telegram)
main.py                 CLI: python main.py {agente} "mensaje"
src/router/graph.py     Grafo LangGraph: estado, nodos, aristas
src/router/prompts.py   Prompts de cada nodo (las reglas viven aquí)
src/router/tools.py     Herramientas del agente (cascarones)
scripts/                Scripts sueltos (probar_router.py)
tests/                  Pruebas pytest
bruno/                  Colección Bruno de la API
```

## Requisitos

- Python 3.12
- Una API key de Google AI Studio (https://aistudio.google.com/apikey)

## Preparar el entorno

```bash
cd api-heroku
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edita `.env` y pon tu `GOOGLE_API_KEY`:

```
GOOGLE_API_KEY=tu_clave_aqui
MODELO=gemini-3.5-flash-lite
```

Nunca subas `.env` al repositorio: está en `.gitignore`.

## Correr el router en local

```bash
source .venv/bin/activate

# Ejecutar un mensaje
python main.py router "quiero comprar una polera azul talla M"

# Ver los nodos por los que pasó y el motivo
python main.py router "mi pedido 4521 llegó roto" --saltos

# Ver el diagrama Mermaid sin ejecutar
python main.py router "" --diagrama

# Los 6 mensajes de referencia
python scripts/probar_router.py
```

Salida esperada de `--saltos`:

```
Saltos: router → agente_postventa
Motivo: El cliente reporta un problema con un pedido ya realizado.
```

Usa `--thread {id}` para mantener conversaciones separadas (por defecto `default`):

```bash
python main.py router "quiero comprar una polera azul" --thread cliente-1
python main.py router "y cuánto cuesta el envío?" --thread cliente-1
```

## Levantar la API

```bash
source .venv/bin/activate
uvicorn api.app:app --reload --port 8000
```

- Swagger interactivo: http://localhost:8000/docs
- OpenAPI JSON: http://localhost:8000/openapi.json
- Health: http://localhost:8000/health

Probar con curl:

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user-42", "texto": "¿tienen la polera azul en talla M?"}'
```

```json
{
  "ruta": "preventa",
  "motivo": "El cliente pregunta por la disponibilidad y talla de un producto antes de comprar.",
  "respuesta": "Soy el agente de preventa. Recibí: ¿tienen la polera azul en talla M?. Pronto podré ayudarte con productos y compras."
}
```

Body inválido (falta `texto`) → `422`:

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user-42"}'
```

Si el modelo falla, la API responde `502` con un mensaje claro y deja el detalle real
solo en el log del servidor.

### Endpoints

| Método | Ruta | Body | Respuesta |
|---|---|---|---|
| `GET` | `/health` | – | `{"ok": true, "modelo": MODELO}` |
| `POST` | `/chat` | `{"user_id": "...", "texto": "..."}` | `{"ruta", "motivo", "respuesta"}` |
| `POST` | `/telegram` | cualquier JSON | `{"ok": true}` |

## Correr las pruebas

```bash
source .venv/bin/activate
pytest -q
```

`tests/test_router.py` no llama al modelo (prueba la estructura del grafo).
`tests/test_api.py` sí hace llamadas reales a Gemini para verificar el ruteo.

## Desplegar en Heroku

1. Crear la app y conectar el repositorio:

   ```bash
   heroku create tu-app
   heroku git:remote -a tu-app
   git push heroku main
   ```

2. Configurar las variables de entorno (nunca subas el `.env`):

   ```bash
   heroku config:set GOOGLE_API_KEY=tu_clave_aqui
   heroku config:set MODELO=gemini-3.5-flash-lite
   heroku config:set TELEGRAM_TOKEN=tu_token_de_botfather
   heroku config:set TELEGRAM_SECRET=un_secreto_aleatorio_y_largo
   heroku config:set PUBLIC_URL=https://tu-app.herokuapp.com
   ```

3. Verificar:

   ```bash
   heroku logs --tail
   curl https://tu-app.herokuapp.com/health
   ```

El `Procfile` ya está listo:

```
web: uvicorn api.app:app --host 0.0.0.0 --port $PORT
```

Y `.python-version` fija Python 3.12 para que Heroku use el runtime correcto.

### Variables de entorno

| Variable | Para qué | Estado |
|---|---|---|
| `GOOGLE_API_KEY` | Autenticación con Gemini | requerida |
| `MODELO` | Modelo del router | `gemini-3.5-flash-lite` |
| `TELEGRAM_TOKEN` | Token del bot de Telegram | vacío hasta la parte 5 |
| `TELEGRAM_SECRET` | Secreto que Telegram manda en cada webhook | `cambiame` (cámbialo) |
| `PUBLIC_URL` | URL https pública | vacío hasta Heroku |

## Conectar Telegram

El endpoint `POST /telegram` ya existe y responde `{"ok": true}`; la parte 5 completa la
verificación del secreto y el envío de la respuesta al chat.

Pasos (los manuales, con el token de BotFather):

1. Crear el bot con [@BotFather](https://t.me/BotFather) y copiar el token en
   `TELEGRAM_TOKEN` (local: `.env`; Heroku: `heroku config:set`).

2. Registrar el webhook apuntando a la URL pública de la API, con el secreto:

   ```bash
   curl -X POST "https://api.telegram.org/bot${TELEGRAM_TOKEN}/setWebhook" \
     -H "Content-Type: application/json" \
     -d "{\"url\": \"${PUBLIC_URL}/telegram\", \"secret_token\": \"${TELEGRAM_SECRET}\"}"
   ```

   Telegram manda ese secreto en el header `X-Telegram-Bot-Api-Secret-Token` de cada
   llamada, y la API debe compararlo con `TELEGRAM_SECRET` antes de procesar el mensaje.

3. Comprobar que quedó registrado:

   ```bash
   curl "https://api.telegram.org/bot${TELEGRAM_TOKEN}/getWebhookInfo"
   ```

4. Probar: abre el chat con tu bot y escribe algo como
   `¿tienen la polera azul en talla M?`. El bot debe responder con la salida del agente
   de preventa.

En local, `PUBLIC_URL` tendría que apuntar a un túnel (ngrok, Cloudflare Tunnel, etc.)
porque Telegram solo llama URLs https públicas.

## Colección Bruno

La carpeta `bruno/` trae `health`, `chat-preventa`, `chat-postventa`, `chat-generica` y
`chat-sin-texto-422` (este último para ver el 422). La variable `baseUrl` está en las
variables de entorno de Bruno:

- `bruno/environments/local.bru` → `http://localhost:8000`
- `bruno/environments/heroku.bru` → `https://TU-APP.herokuapp.com` (pon la tuya)

Cambia el entorno activo en la pestaña **Environments** de Bruno para pasar de local a Heroku.

## Convenciones del proyecto

Ver [AGENTS.md](AGENTS.md) para las reglas de estructura de agentes, CLI, API y despliegue.
