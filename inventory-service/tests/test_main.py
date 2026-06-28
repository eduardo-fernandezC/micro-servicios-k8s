"""
Tests unitarios de inventory-service.

Cubren la consulta de stock y la reserva, incluyendo los caminos de error
(producto inexistente -> 404, stock insuficiente -> 409, cantidad inválida -> 422).
El stock vive en memoria; cada test usa un producto distinto para no depender
del orden de ejecución.
"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["service"] == "inventory-service"


def test_get_inventory_ok():
    r = client.get("/inventory/1")
    assert r.status_code == 200
    body = r.json()
    assert body["product_id"] == 1
    assert body["available"] >= 0


def test_get_inventory_not_found():
    r = client.get("/inventory/999")
    assert r.status_code == 404


def test_reserve_ok():
    # El producto 2 arranca con stock 100; reservamos 5.
    r = client.post("/inventory/2/reserve", json={"quantity": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["reserved"] == 5
    assert body["remaining"] == 95


def test_reserve_insufficient_stock():
    # El producto 3 arranca con stock 8; pedir 999 debe dar 409 (no descuenta).
    r = client.post("/inventory/3/reserve", json={"quantity": 999})
    assert r.status_code == 409
    assert "insuficiente" in r.json()["detail"].lower()


def test_reserve_product_not_found():
    r = client.post("/inventory/999/reserve", json={"quantity": 1})
    assert r.status_code == 404


def test_reserve_invalid_quantity():
    # quantity debe ser > 0; pydantic responde 422 antes de tocar el stock.
    r = client.post("/inventory/1/reserve", json={"quantity": 0})
    assert r.status_code == 422
