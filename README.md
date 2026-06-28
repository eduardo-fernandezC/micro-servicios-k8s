# Laboratorio de Microservicios en EKS — ISY1101 Herramientas DevOps (Módulo 3)

Laboratorio práctico de una arquitectura de microservicios sencilla para una
**tienda online**. Tres servicios backend (Python + FastAPI) que se comunican
entre sí vía HTTP interno. El objetivo es practicar:

- Despliegue en **Amazon EKS**.
- **Comunicación inter-servicio** mediante `ClusterIP` y DNS interno de Kubernetes.
- Publicación de imágenes en **Amazon ECR**.
- Conexión posterior de un pipeline de **GitHub Actions** (CI/CD).

---

## 1. Arquitectura

```
                         ┌─────────────────────┐
   POST /orders ───────► │   orders-service     │  (8003)  ← punto de entrada
                         │   (orquestador)      │
                         └──────────┬───────────┘
                          HTTP      │      HTTP
              ┌──────────────────┐  │  ┌────────────────────┐
              ▼                  │     ▼                    │
   ┌─────────────────────┐      │  ┌──────────────────────┐
   │  products-service   │(8001)│  │  inventory-service   │(8002)
   │  catálogo/precios   │      │  │  stock / reservas    │
   └─────────────────────┘      │  └──────────────────────┘
```

| Servicio            | Puerto | Responsabilidad                         | Depende de                       |
|---------------------|--------|-----------------------------------------|----------------------------------|
| `products-service`  | 8001   | Catálogo de productos (id, nombre, precio) | — (servicio hoja)             |
| `inventory-service` | 8002   | Stock disponible y reservas             | —                                |
| `orders-service`    | 8003   | Crear pedidos (orquesta el flujo)       | products-service, inventory-service |

**Flujo de un pedido (`POST /orders`)**:
1. `orders-service` consulta el producto en `products-service` (precio + nombre).
2. Pide a `inventory-service` que reserve el stock.
3. Si ambos pasos van bien, registra el pedido y devuelve el total.

> El código **no cambia** entre local y EKS. Solo cambia la configuración
> (variables de entorno `PRODUCTS_SERVICE_URL` / `INVENTORY_SERVICE_URL`),
> porque tanto Docker Compose como Kubernetes resuelven los servicios por nombre.

---

## 2. Estructura del proyecto

```
micro-servicios-k8s/
├── docker-compose.yml          # Levanta los 3 servicios localmente
├── README.md
├── scripts/
│   ├── build-and-push-ecr.sh   # Construye y publica imágenes en ECR
│   └── deploy-eks.sh           # Aplica los manifiestos en el clúster
├── products-service/
│   ├── app/main.py
│   ├── requirements.txt
│   ├── requirements-dev.txt    # dependencias de test (pytest, pytest-cov, …)
│   ├── pytest.ini              # config de pytest + umbral de cobertura (70%)
│   ├── tests/
│   │   └── test_main.py        # tests unitarios
│   ├── Dockerfile
│   └── k8s/
│       ├── deployment.yaml
│       └── service.yaml
├── inventory-service/          # (misma estructura)
└── orders-service/             # (misma estructura; tests con respx)
```

---

## 3. Paso A — Probar localmente con Docker Compose

```bash
docker compose up --build
```

Verificar que cada servicio responde:

```bash
curl http://localhost:8001/health     # products-service
curl http://localhost:8002/health     # inventory-service
curl http://localhost:8003/health     # orders-service
curl http://localhost:8003/config     # ver a qué URLs internas apunta orders
```

**Probar el flujo completo (comunicación inter-servicio):**

```bash
# Crear un pedido: orders llama a products + inventory por detrás
curl -X POST http://localhost:8003/orders \
     -H "Content-Type: application/json" \
     -d '{"product_id": 1, "quantity": 2}'

# Listar pedidos
curl http://localhost:8003/orders

# Ver cómo se descontó el stock
curl http://localhost:8002/inventory/1
```

**Probar el manejo de errores entre servicios** (stock insuficiente → 409):

```bash
curl -i -X POST http://localhost:8003/orders \
     -H "Content-Type: application/json" \
     -d '{"product_id": 3, "quantity": 999}'
```

Cada servicio expone documentación interactiva en `/docs` (Swagger UI),
por ejemplo http://localhost:8003/docs.

Para detener:

```bash
docker compose down
```

---

## 4. Paso B — Publicar imágenes en Amazon ECR

```bash
export AWS_ACCOUNT_ID=123456789012   # ← tu Account ID
export AWS_REGION=us-east-1          # ← tu región

./scripts/build-and-push-ecr.sh
```

El script crea los repositorios en ECR (si no existen), construye las 3 imágenes
y las sube como `:latest`.

Luego reemplaza los marcadores en los `deployment.yaml`:

```bash
sed -i '' "s|<ACCOUNT_ID>|${AWS_ACCOUNT_ID}|g; s|<REGION>|${AWS_REGION}|g" */k8s/deployment.yaml
# (En Linux usa 'sed -i' sin las comillas vacías)
```

---

## 5. Paso C — Desplegar en EKS

Configura el acceso a tu clúster:

```bash
aws eks update-kubeconfig --name <nombre-del-cluster> --region ${AWS_REGION}
```

Aplica los manifiestos:

```bash
./scripts/deploy-eks.sh
```

Comprueba el estado:

```bash
kubectl get pods
kubectl get svc
```

**Verificar la comunicación inter-servicio dentro del clúster.**
Como todos los `Service` son `ClusterIP` (solo accesibles internamente), usamos
`port-forward` para alcanzar `orders-service` desde tu máquina:

```bash
kubectl port-forward svc/orders-service 8003:8003
```

En otra terminal:

```bash
curl -X POST http://localhost:8003/orders \
     -H "Content-Type: application/json" \
     -d '{"product_id": 2, "quantity": 1}'
```

Si esto funciona, significa que dentro del clúster `orders-service` resolvió
`http://products-service:8001` y `http://inventory-service:8002` por **DNS
interno de Kubernetes** — el objetivo central del laboratorio. ✅

> **Tip didáctico**: ejecuta `kubectl exec -it deploy/orders-service -- \
> python -c "import urllib.request; print(urllib.request.urlopen('http://products-service:8001/health').read())"`
> para ver la resolución DNS interna en acción desde dentro de un pod.

---

## 6. Tests unitarios y cobertura

Cada microservicio incluye **tests unitarios** con `pytest` y medición de
cobertura con `pytest-cov`. La configuración (`pytest.ini` de cada servicio)
exige un mínimo de **70% de cobertura**: si baja de ahí, `pytest` falla.

| Servicio            | Qué cubren los tests                                              | Cobertura |
|---------------------|------------------------------------------------------------------|-----------|
| `products-service`  | `/health`, `/products`, `/products/{id}` (200 y 404)             | 100%      |
| `inventory-service` | consulta de stock y reserva (200, 404, 409 sin stock, 422)       | 100%      |
| `orders-service`    | flujo de pedido completo + errores (404, 409, 503) usando `respx`| 100%      |

> En `orders-service` los tests son **unitarios de verdad**: no levantan a
> `products-service` ni a `inventory-service`. Las llamadas HTTP salientes se
> simulan con [`respx`](https://lundberg.github.io/respx/), así que el test
> verifica solo la lógica del orquestador.

### Correr los tests de un servicio

**Con Python local** (entra a la carpeta del servicio):

```bash
cd products-service
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

`pytest` toma la configuración de `pytest.ini` automáticamente (mide cobertura
sobre `app/` y aplica el umbral del 70%).

**Con Docker** (misma imagen `python:3.12-slim` que usa el servicio, sin instalar
nada en tu máquina):

```bash
docker run --rm -v "$PWD/products-service":/svc -w /svc python:3.12-slim \
  bash -c "pip install -q -r requirements.txt -r requirements-dev.txt && pytest"
```

Repite cambiando `products-service` por `inventory-service` u `orders-service`.

> El umbral del 70% está pensado para que un pipeline de CI lo use como
> **compuerta de calidad**: `pytest` devuelve un código de salida distinto de
> cero si la cobertura no se alcanza, lo que pone el job en rojo.

---

## 7. Siguiente paso — CI/CD con GitHub Actions

La estructura ya está lista para un pipeline. Un workflow típico haría:

1. **Login a ECR** con credenciales (rol OIDC o secretos).
2. **Build & push** de las 3 imágenes (reutilizando la lógica de `build-and-push-ecr.sh`).
3. **`kubectl apply`** o `kubectl set image` para desplegar en EKS.

Cada servicio es independiente, así que el pipeline puede usar una *matrix*
sobre `[products-service, inventory-service, orders-service]`.

---

## Notas

- Datos en memoria (didáctico): al reiniciar un pod, el stock y los pedidos se
  reinician. En un caso real cada servicio tendría su propia base de datos.
- `replicas: 2` en cada deployment para mostrar balanceo entre pods vía el Service.
- Las probes `liveness`/`readiness` usan el endpoint `/health`.
