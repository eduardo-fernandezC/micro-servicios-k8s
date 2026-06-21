"""
inventory-service
==================
Microservicio de INVENTARIO / stock.

Responsabilidad única: llevar el stock disponible por producto y permitir
"reservar" unidades cuando se crea un pedido.

Es consumido por orders-service vía HTTP interno:
  - GET  /inventory/{product_id}          -> consultar stock
  - POST /inventory/{product_id}/reserve  -> descontar stock al confirmar pedido
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import time
import psutil

INICIO = time.time()   # momento en que arranco el proceso (para el uptime)

app = FastAPI(
    title="Inventory Service",
    description="Control de stock de la tienda (Módulo 3 - ISY1101)",
    version="1.0.0",
)

# Stock inicial en memoria: product_id -> unidades disponibles.
STOCK = {
    1: 25,
    2: 100,
    3: 8,
    4: 40,
}

class ReserveRequest(BaseModel):
    """Cuerpo de la petición para reservar stock."""
    quantity: int = Field(gt=0, description="Cantidad de unidades a reservar")

@app.get("/live")
def live():
    """
    Liveness: el proceso esta vivo y respondiendo. NO depende de nadie externo.
    Devolvemos OK y desde hace cuantos segundos esta arriba (uptime).
    """
    return {"alive": True, "uptime_segundos": round(time.time() - INICIO, 1)}


@app.get("/ready")
def ready():
    """Readiness: listo solo si NO esta saturado de memoria (uso real con psutil)."""
    memoria_usada = psutil.virtual_memory().percent
    if memoria_usada > 90:
        raise HTTPException(status_code=503, detail={"ready": False, "memoria_%": memoria_usada})
    return {"ready": True, "memoria_%": memoria_usada, "service": "products-service"}

@app.get("/health")
def health():
    return {"status": "ok", "service": "inventory-service"}

@app.get("/inventory/{product_id}")
def get_inventory(product_id: int):
    """Consulta el stock disponible de un producto."""
    if product_id not in STOCK:
        raise HTTPException(status_code=404, detail=f"Producto {product_id} sin registro de stock")
    return {"product_id": product_id, "available": STOCK[product_id]}

@app.post("/inventory/{product_id}/reserve")
def reserve_inventory(product_id: int, body: ReserveRequest):
    """
    Reserva (descuenta) unidades de stock.
    Devuelve 409 si no hay stock suficiente; útil para que los estudiantes
    vean cómo orders-service maneja un error que viene de otro servicio.
    """
    if product_id not in STOCK:
        raise HTTPException(status_code=404, detail=f"Producto {product_id} sin registro de stock")

    available = STOCK[product_id]
    if body.quantity > available:
        raise HTTPException(
            status_code=409,
            detail=f"Stock insuficiente: disponible {available}, solicitado {body.quantity}",
        )

    STOCK[product_id] = available - body.quantity
    return {
        "product_id": product_id,
        "reserved": body.quantity,
        "remaining": STOCK[product_id],
    }
