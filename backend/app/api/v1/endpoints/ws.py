"""WebSocket route: /ws/market (registered at app root, no /api/v1 prefix)."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.websocket import events
from app.websocket.manager import manager

router = APIRouter()


@router.websocket("/ws/market")
async def ws_market(websocket: WebSocket) -> None:
    """Realtime feed: quotes ticks, new BOF signals, market-status flips.

    Protocol: server pushes JSON envelopes `{type, data}`; client may send the
    literal text `ping` and receives a `pong` envelope. Heartbeats keep NATs
    alive; dead sockets are pruned on first failed broadcast.
    """
    await manager.connect(websocket)
    try:
        await manager.send_personal(
            websocket,
            events.hello_payload(settings.DEMO_TICK_SECONDS, settings.MARKET_DATA_PROVIDER),
        )
        while True:
            message = await websocket.receive_text()
            if message.strip().lower() == "ping":
                await manager.send_personal(websocket, events.pong_payload())
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket)
