"""
Tests unitarios de orders-service (el orquestador).

orders-service llama por HTTP a products-service e inventory-service. Para que
estos tests sean UNITARIOS (sin levantar los otros servicios), simulamos esas
llamadas con `respx`, que intercepta las peticiones salientes de httpx.

Detalle importante: el TestClient de FastAPI usa un transporte ASGI en memoria,
que respx NO intercepta. Por eso las peticiones del test hacia la app funcionan
normal, mientras que las peticiones que la app hace hacia products/inventory sí
quedan simuladas. Justo lo que queremos.
"""
import httpx
import respx
from fastapi.testclient import TestClient

from app.main import app, ORDERS, PRODUCTS_SERVICE_URL, INVENTORY_SERVICE_URL

client = TestClient(app)


def setup_function():
    # La "base de datos" de pedidos vive en memoria; la limpiamos antes de cada test.
    ORDERS.clear()


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["service"] == "orders-service"


def test_config():
    r = client.get("/config")
    body = r.json()
    assert body["products_service_url"] == PRODUCTS_SERVICE_URL
    assert body["inventory_service_url"] == INVENTORY_SERVICE_URL


def test_list_orders_empty():
    r = client.get("/orders")
    assert r.status_code == 200
    assert r.json() == {"orders": []}


@respx.mock
def test_create_order_ok():
    respx.get(f"{PRODUCTS_SERVICE_URL}/products/1").mock(
        return_value=httpx.Response(
            200, json={"id": 1, "name": "Teclado mecánico", "price": 39990}
        )
    )
    respx.post(f"{INVENTORY_SERVICE_URL}/inventory/1/reserve").mock(
        return_value=httpx.Response(
            200, json={"product_id": 1, "reserved": 2, "remaining": 23}
        )
    )

    r = client.post("/orders", json={"product_id": 1, "quantity": 2})

    assert r.status_code == 201
    body = r.json()
    assert body["product_name"] == "Teclado mecánico"
    assert body["total"] == 39990 * 2
    assert body["stock_remaining"] == 23

    # El pedido quedó registrado y se puede listar.
    listed = client.get("/orders").json()["orders"]
    assert len(listed) == 1


@respx.mock
def test_create_order_product_not_found():
    respx.get(f"{PRODUCTS_SERVICE_URL}/products/999").mock(
        return_value=httpx.Response(404, json={"detail": "no existe"})
    )

    r = client.post("/orders", json={"product_id": 999, "quantity": 1})

    assert r.status_code == 404


@respx.mock
def test_create_order_insufficient_stock():
    respx.get(f"{PRODUCTS_SERVICE_URL}/products/3").mock(
        return_value=httpx.Response(
            200, json={"id": 3, "name": "Monitor 27 pulgadas", "price": 159990}
        )
    )
    respx.post(f"{INVENTORY_SERVICE_URL}/inventory/3/reserve").mock(
        return_value=httpx.Response(409, json={"detail": "Stock insuficiente"})
    )

    r = client.post("/orders", json={"product_id": 3, "quantity": 999})

    assert r.status_code == 409
    assert "insuficiente" in r.json()["detail"].lower()


@respx.mock
def test_create_order_products_service_down():
    respx.get(f"{PRODUCTS_SERVICE_URL}/products/1").mock(
        side_effect=httpx.ConnectError("connection refused")
    )

    r = client.post("/orders", json={"product_id": 1, "quantity": 1})

    assert r.status_code == 503
    assert "products-service" in r.json()["detail"]


@respx.mock
def test_create_order_inventory_service_down():
    respx.get(f"{PRODUCTS_SERVICE_URL}/products/1").mock(
        return_value=httpx.Response(
            200, json={"id": 1, "name": "Teclado mecánico", "price": 39990}
        )
    )
    respx.post(f"{INVENTORY_SERVICE_URL}/inventory/1/reserve").mock(
        side_effect=httpx.ConnectError("connection refused")
    )

    r = client.post("/orders", json={"product_id": 1, "quantity": 1})

    assert r.status_code == 503
    assert "inventory-service" in r.json()["detail"]


def test_create_order_invalid_quantity():
    # quantity debe ser > 0; pydantic responde 422 sin llamar a los otros servicios.
    r = client.post("/orders", json={"product_id": 1, "quantity": 0})
    assert r.status_code == 422
