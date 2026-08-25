"""WebSocket endpoint tests (TestClient-managed lifespan not required)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.websocket import events
from app.websocket.manager import manager


@pytest.fixture()
def client():
    with TestClient(app) as c:  # runs lifespan; live loop disabled in tests via env
        yield c


def test_hello_on_connect(client):
    with client.websocket_connect("/ws/market") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello"
        assert hello["data"]["provider"] in ("demo", "twelve_data")  # falls back gracefully
        # is_demo reflects actual data source (True when demo fallback)


def test_ping_pong(client):
    with client.websocket_connect("/ws/market") as ws:
        ws.receive_json()  # hello
        ws.send_text("ping")
        assert ws.receive_json()["type"] == "pong"


def test_broadcast_reaches_all_clients(client):
    with client.websocket_connect("/ws/market") as a, \
         client.websocket_connect("/ws/market") as b:
        a.receive_json(), b.receive_json()

        payload = events.quote_ticks_payload([
            {"symbol": "TCS", "last_price": 4321.5, "change_pct": 0.42,
             "direction": "UP", "is_demo": True}
        ])
        sent = __import__("asyncio").run(manager.broadcast(payload))
        assert sent == 2

        ma = a.receive_json()
        mb = b.receive_json()
        assert ma["type"] == "quotes" and mb["type"] == "quotes"
        assert ma["data"][0]["symbol"] == "TCS"


def test_disconnect_prunes_client(client):
    with client.websocket_connect("/ws/market") as ws:
        ws.receive_json()
        assert manager.count == 1
    # after context exit the socket closes; give the server a beat
    client.get("/healthz")
    assert manager.count == 0


def test_payload_builders_shape():
    sig = events.signals_payload([{"id": "x", "symbol": "TCS"}])
    assert sig["type"] == "signals" and sig["data"][0]["symbol"] == "TCS"

    st = events.market_status_payload("NSE", "OPEN")
    assert st["type"] == "market_status" and st["data"]["status"] == "OPEN"

    assert events.pong_payload() == {"type": "pong"}
