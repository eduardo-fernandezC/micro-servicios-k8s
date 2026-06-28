"""
Tests unitarios de products-service.

Usan el TestClient de FastAPI, que ejecuta la aplicación en memoria (sin red ni
servidor). products-service no depende de ningún otro servicio, así que estos
tests no necesitan simular nada externo.
"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"service": "ROTO"}


def test_list_products():
    r = client.get("/products")
    assert r.status_code == 200
    products = r.json()["products"]
    assert len(products) == 4
    assert any(p["name"] == "Teclado mecánico" for p in products)


def test_get_product_ok():
    r = client.get("/products/1")
    assert r.status_code == 200
    assert r.json() == {"id": 1, "name": "Teclado mecánico", "price": 39990}


def test_get_product_not_found():
    r = client.get("/products/999")
    assert r.status_code == 404
    assert "no encontrado" in r.json()["detail"]
