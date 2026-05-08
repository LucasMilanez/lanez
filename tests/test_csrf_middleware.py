"""Testes do CSRFMiddleware — defesa em profundidade.

Regras:
- Métodos seguros (GET/HEAD/OPTIONS) passam
- Bearer auth passa (clientes MCP)
- Endpoints exemptos passam (/auth/callback, /webhooks/graph, /healthz, /readyz)
- Cookie auth + mutação sem header → 403
- Cookie auth + mutação com header → passa
- Sem cookie nem Bearer → passa (auth falha 401 depois)
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.csrf import CSRFMiddleware


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(CSRFMiddleware)

    @app.get("/ping")
    def ping() -> dict:
        return {"ok": True}

    @app.post("/mutate")
    def mutate() -> dict:
        return {"ok": True}

    @app.delete("/remove")
    def remove() -> dict:
        return {"ok": True}

    @app.post("/auth/callback")
    def cb() -> dict:
        return {"ok": True}

    @app.post("/webhooks/graph")
    def wh() -> dict:
        return {"ok": True}

    return app


def test_get_always_passes():
    client = TestClient(_build_app())
    client.cookies.set("lanez_session", "some-token")
    resp = client.get("/ping")
    assert resp.status_code == 200


def test_post_with_bearer_passes():
    client = TestClient(_build_app())
    resp = client.post("/mutate", headers={"Authorization": "Bearer xyz"})
    assert resp.status_code == 200


def test_post_without_cookie_passes():
    """Sem cookie nem Bearer: middleware deixa passar (auth falha depois)."""
    client = TestClient(_build_app())
    resp = client.post("/mutate")
    assert resp.status_code == 200


def test_post_cookie_without_header_is_forbidden():
    client = TestClient(_build_app())
    client.cookies.set("lanez_session", "some-token")
    resp = client.post("/mutate")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Missing CSRF header"


def test_post_cookie_with_header_passes():
    client = TestClient(_build_app())
    client.cookies.set("lanez_session", "some-token")
    resp = client.post("/mutate", headers={"X-Requested-With": "XMLHttpRequest"})
    assert resp.status_code == 200


def test_delete_cookie_without_header_is_forbidden():
    client = TestClient(_build_app())
    client.cookies.set("lanez_session", "some-token")
    resp = client.delete("/remove")
    assert resp.status_code == 403


def test_auth_callback_is_exempt():
    """OAuth callback vem do Entra ID — não pode exigir header do nosso frontend."""
    client = TestClient(_build_app())
    resp = client.post("/auth/callback")
    assert resp.status_code == 200


def test_webhooks_graph_is_exempt():
    """Microsoft Graph não envia X-Requested-With."""
    client = TestClient(_build_app())
    resp = client.post("/webhooks/graph")
    assert resp.status_code == 200


def test_wrong_header_value_is_forbidden():
    client = TestClient(_build_app())
    client.cookies.set("lanez_session", "some-token")
    resp = client.post("/mutate", headers={"X-Requested-With": "fetch"})
    assert resp.status_code == 403
