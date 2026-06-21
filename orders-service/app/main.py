import os
import time
import psutil

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(
    title="Orders Service",
    description="Gestión de pedidos de la tienda (Módulo 3 - ISY1101)",
    version="1.0.0",
)

# Configuración vía variables de entorno
PRODUCTS_SERVICE_URL = os.getenv(
    "PRODUCTS_SERVICE_URL",
    "http://localhost:8001"
)

INVENTORY_SERVICE_URL = os.getenv(
    "INVENTORY_SERVICE_URL",
    "http://localhost:8002"
)

INICIO = time.time()

READY_MAX_MEM_PERCENT = float(
    os.getenv("READY_MAX_MEM_PERCENT", "90")
)

# Base de datos en memoria
ORDERS = []


class OrderRequest(BaseModel):
    product_id: int = Field(description="Id del producto a pedir")
    quantity: int = Field(gt=0, description="Cantidad de unidades")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "orders-service"
    }


@app.get("/live")
def live():
    """
    Liveness: el proceso está vivo.
    """
    return {
        "alive": True,
        "uptime_segundos": round(time.time() - INICIO, 1)
    }


@app.get("/ready")
def ready():
    """
    Readiness basada en uso real de CPU y memoria.
    """
    cpu = psutil.cpu_percent(interval=0.1)
    memoria = psutil.virtual_memory().percent

    if memoria > READY_MAX_MEM_PERCENT:
        raise HTTPException(
            status_code=503,
            detail={
                "ready": False,
                "cpu_%": cpu,
                "memoria_%": memoria,
                "umbral_%": READY_MAX_MEM_PERCENT
            }
        )

    return {
        "ready": True,
        "cpu_%": cpu,
        "memoria_%": memoria
    }


@app.get("/config")
def config():
    return {
        "products_service_url": PRODUCTS_SERVICE_URL,
        "inventory_service_url": INVENTORY_SERVICE_URL,
    }


@app.get("/orders")
def list_orders():
    return {"orders": ORDERS}


@app.post("/orders", status_code=201)
def create_order(order: OrderRequest):

    with httpx.Client(timeout=5.0) as client:

        try:
            resp = client.get(
                f"{PRODUCTS_SERVICE_URL}/products/{order.product_id}"
            )

        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"No se pudo contactar products-service: {exc}",
            )

        if resp.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail=f"Producto {order.product_id} no existe"
            )

        resp.raise_for_status()
        product = resp.json()

        try:
            inv_resp = client.post(
                f"{INVENTORY_SERVICE_URL}/inventory/{order.product_id}/reserve",
                json={"quantity": order.quantity},
            )

        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"No se pudo contactar inventory-service: {exc}",
            )

        if inv_resp.status_code == 409:
            raise HTTPException(
                status_code=409,
                detail=inv_resp.json().get("detail")
            )

        inv_resp.raise_for_status()
        reservation = inv_resp.json()

    order_record = {
        "order_id": len(ORDERS) + 1,
        "product_id": product["id"],
        "product_name": product["name"],
        "unit_price": product["price"],
        "quantity": order.quantity,
        "total": product["price"] * order.quantity,
        "stock_remaining": reservation["remaining"],
    }

    ORDERS.append(order_record)

    return order_record