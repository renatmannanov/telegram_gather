"""
HTTP API for telegram-gather.

Exposes Telethon data over authenticated HTTP endpoints.
Runs inside the same event loop as the Telethon client.

Endpoints:
    GET /api/messages?chat=<name|id>&period=<1d|1w|2w>&limit=200
    GET /api/chats

All requests require: Authorization: Bearer <TG_GATHER_API_KEY>
"""
import logging
import os
from datetime import datetime, timezone

from aiohttp import web

from fetch_chat import resolve_chat, fetch_messages, parse_period

logger = logging.getLogger(__name__)


def _get_api_key() -> str | None:
    return os.getenv("TG_GATHER_API_KEY")


@web.middleware
async def auth_middleware(request, handler):
    """Check Bearer token on every request."""
    api_key = _get_api_key()
    if not api_key:
        # Should not happen — start_api guards this
        return web.json_response({"error": "API key not configured"}, status=500)

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return web.json_response({"error": "Missing Authorization header"}, status=401)

    token = auth_header[len("Bearer "):]
    if token != api_key:
        return web.json_response({"error": "Invalid API key"}, status=401)

    return await handler(request)


async def handle_messages(request):
    """GET /api/messages?chat=<name>&period=1w&limit=200"""
    client = request.app["telethon_client"]

    chat = request.query.get("chat")
    if not chat:
        return web.json_response({"error": "Missing 'chat' parameter"}, status=400)

    period = request.query.get("period", "1w")
    limit = int(request.query.get("limit", "200"))

    try:
        # Numeric ID — fast path (no dialog iteration)
        if chat.lstrip("-").isdigit():
            entity = await client.get_entity(int(chat))
        else:
            entity = await resolve_chat(client, chat)
    except Exception as e:
        return web.json_response({"error": f"Chat not found: {e}"}, status=404)

    delta = parse_period(period)
    since = datetime.now(timezone.utc) - delta

    try:
        messages = await fetch_messages(client, entity, since, limit)
    except Exception as e:
        logger.error(f"Failed to fetch messages: {e}")
        return web.json_response({"error": f"Failed to fetch messages: {e}"}, status=500)

    # Ensure dates are timezone-aware UTC (fetch_messages uses naive strftime)
    for msg in messages:
        if msg.get("date") and "+" not in msg["date"] and "Z" not in msg["date"]:
            msg["date"] = msg["date"] + "+00:00"

    # Get chat title
    chat_name = getattr(entity, "title", None) or getattr(entity, "first_name", chat)
    chat_id = getattr(entity, "id", None)

    return web.json_response({
        "chat_name": chat_name,
        "chat_id": chat_id,
        "period": period,
        "message_count": len(messages),
        "messages": messages,
    })


async def handle_chats(request):
    """GET /api/chats — list available dialogs."""
    client = request.app["telethon_client"]

    chats = []
    async for dialog in client.iter_dialogs():
        chat_type = "user"
        if dialog.is_group:
            chat_type = "group"
        elif dialog.is_channel:
            chat_type = "channel"

        chats.append({
            "id": dialog.id,
            "name": dialog.title or dialog.name,
            "type": chat_type,
        })

    return web.json_response({"chats": chats})


async def start_api(client, port: int = 8080):
    """Start aiohttp server in the background.

    Must be called inside the same event loop as Telethon client.
    Returns the runner so it can be cleaned up on shutdown.
    """
    api_key = _get_api_key()
    if not api_key:
        logger.warning("TG_GATHER_API_KEY not set — HTTP API disabled")
        return None

    app = web.Application(middlewares=[auth_middleware])
    app["telethon_client"] = client

    app.router.add_get("/api/messages", handle_messages)
    app.router.add_get("/api/chats", handle_chats)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    logger.info(f"HTTP API started on port {port}")
    return runner
