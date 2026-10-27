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
scripts/set_webhook.py   Registra la URL y el secreto del webhook de Telegram
scripts/webhook_info.py  Consulta el estado del webhook y sus errores
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
| `POST` | `/telegram` | Update de Telegram + cabecera de secreto | `{"ok": true}`; `403` si el secreto falta o es incorrecto |

## Correr las pruebas

```bash
source .venv/bin/activate
pytest -q
```

`tests/test_router.py` no llama al modelo (prueba la estructura del grafo).
`tests/test_api.py` sí hace llamadas reales a Gemini para verificar el ruteo.
Las pruebas de Telegram usan un grafo simulado y transporte HTTP de prueba, sin llamadas
externas. Para ejecutar toda la suite local excluyendo los tres casos reales de Gemini:

```bash
pytest -q -k 'not test_chat_rutea'
```

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
   ```

   Para conectar el bot después, sigue la sección **Telegram**.

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
| `TELEGRAM_TOKEN` | Token del bot de Telegram | requerido para enviar respuestas |
| `TELEGRAM_SECRET` | Secreto que Telegram manda en cada webhook | `cambiame` (cámbialo) |
| `PUBLIC_URL` | URL https pública usada por `set_webhook.py` | requerida al registrar el webhook |

## Telegram

Primero crea tu bot hablando con [@BotFather](https://t.me/BotFather): envía `/newbot`,
elige su nombre y copia el token a `TELEGRAM_TOKEN` en tu `.env` local. Elige también
un `TELEGRAM_SECRET` propio y largo, usando letras, números, `_` o `-`:

```dotenv
TELEGRAM_TOKEN=tu_token_de_botfather
TELEGRAM_SECRET=tu_secreto_aleatorio_y_largo
PUBLIC_URL=https://tu-app.herokuapp.com
```

La integración usa `httpx`, sin librerías de bot. `POST /telegram` verifica la cabecera
`X-Telegram-Bot-Api-Secret-Token` contra `TELEGRAM_SECRET`: si falta, no coincide o el
servidor no tiene secreto configurado, responde `403`. Los updates autenticados sin
`message.text` se ignoran con `200`.

Para un mensaje de texto, extrae `message.chat.id`, ejecuta el grafo con
`thread_id=str(chat_id)` y envía `respuesta` al chat mediante `sendMessage`.
Las respuestas largas se dividen en mensajes consecutivos de hasta 4096 caracteres.
La memoria se conserva por chat dentro del proceso y se pierde al reiniciar el dyno.
El webhook devuelve `200` después de procesar y enviar; si el modelo tarda, esa respuesta
HTTP también espera. Los errores del modelo o del envío se registran y aun así se devuelve
`200`, por lo que ese estado confirma la recepción del update, no la entrega de la respuesta.
Los métodos y la cabecera siguen la [Bot API oficial de Telegram](https://core.telegram.org/bots/api).

Con la app de Heroku creada y las variables de Gemini configuradas, completa estos pasos
desde la raíz del repositorio, en este orden:

1. **Configura el token y el secreto en Heroku**, con los mismos valores que en `.env`:

   ```bash
   heroku config:set TELEGRAM_TOKEN='tu_token_de_botfather' TELEGRAM_SECRET='tu_secreto_aleatorio_y_largo'
   ```

2. **Haz commit y push a GitHub y a Heroku**:

   ```bash
   git add api/app.py scripts/ tests/ README.md
   git commit -m "Conectar el router a Telegram con httpx"
   git push origin HEAD
   git push heroku HEAD:main
   ```

3. **Registra y confirma el webhook**. Pon en el `.env` local `PUBLIC_URL` con la URL
   HTTPS real de Heroku, sin `/telegram`; el script agrega ese sufijo. Luego ejecuta:

   ```bash
   source .venv/bin/activate
   python scripts/set_webhook.py
   python scripts/webhook_info.py
   ```

   Ambos scripts imprimen la respuesta de Telegram. Confirma `ok: true`, que
   `result.url` sea `https://tu-app.herokuapp.com/telegram` y revisa
   `pending_update_count` y `last_error_message` en la información del webhook.
   `PUBLIC_URL` se necesita localmente para registrar el webhook; la API no la usa al recibirlo.

4. **Escribe al bot los seis mensajes del prompt 2**, los mismos de
   `scripts/probar_router.py`, y verifica la ruta de cada uno en los logs:

   ```bash
   heroku logs --tail
   ```

   | Mensaje | Ruta esperada |
   |---|---|
   | ¿tienen la polera azul en talla M? | `preventa` |
   | mi pedido 4521 llegó roto | `postventa` |
   | hola | `generica` |
   | ¿cuánto cuesta el envío a Valparaíso? | `preventa` |
   | quiero devolver unas zapatillas | `postventa` |
   | ¿qué hora es en Tokio? | `generica` |

   Busca las entradas con `chat_id`, `ruta` y `motivo`, y confirma que llegue la respuesta
   al chat. Revisa el motivo si el historial de ese chat cambia la interpretación del mensaje.

5. **Si el bot no responde**, ejecuta otra vez `python scripts/webhook_info.py` y revisa:

   - El webhook debe apuntar a `/telegram` en una URL pública **HTTPS**.
   - `TELEGRAM_SECRET` debe ser igual en Heroku y en el `.env` con el que ejecutaste
     `set_webhook.py`; vuelve a registrar el webhook si cambiaste el secreto. Un `403`
     indica que falta o no coincide.
   - `TELEGRAM_TOKEN` debe ser el token correcto de BotFather en ambos entornos.
   - `pending_update_count` indica updates pendientes; `last_error_message` y
     `last_error_date` muestran el último error de entrega del webhook. Para fallos
     del modelo o de `sendMessage`, consulta `heroku logs --tail`.

### Prueba local opcional con Cloudflare Tunnel

Con las variables de Gemini y Telegram en `.env`, inicia la API:

```bash
uvicorn api.app:app --reload --port 8000
```

En otra terminal, con `cloudflared` instalado:

```bash
cloudflared tunnel --url http://localhost:8000
```

Copia la URL HTTPS que entrega el túnel a `PUBLIC_URL` en `.env` y ejecuta
`python scripts/set_webhook.py` y `python scripts/webhook_info.py`. Mantén la API y el
túnel abiertos para escribirle al bot. El registro cambia el destino del webhook de ese
bot: al desplegar, restaura `PUBLIC_URL` a la URL de Heroku y vuelve a ejecutar ambos scripts.

## Colección Bruno

La carpeta `bruno/` trae `health`, `chat-preventa`, `chat-postventa`, `chat-generica` y
`chat-sin-texto-422` (este último para ver el 422). La variable `baseUrl` está en las
variables de entorno de Bruno:

- `bruno/environments/local.bru` → `http://localhost:8000`
- `bruno/environments/heroku.bru` → `https://TU-APP.herokuapp.com` (pon la tuya)

Cambia el entorno activo en la pestaña **Environments** de Bruno para pasar de local a Heroku.

## Convenciones del proyecto

Ver [AGENTS.md](AGENTS.md) para las reglas de estructura de agentes, CLI, API y despliegue.
