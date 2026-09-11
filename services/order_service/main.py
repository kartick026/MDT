"""
Order Service
Handles order management, communicates with User service
"""
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import uuid
import httpx

app = FastAPI(title="Order Service", version="1.0.0")

# In-memory database
orders_db = {}
order_counter = 1000

# Service URLs
USER_SERVICE_URL = "http://user-service:8001"
# Broken dependency to dead/unresolvable host
INVENTORY_SERVICE_URL = "http://inventory-service:9999/api/v1/inventory/reserve"


class OrderItem(BaseModel):
    product_id: str
    quantity: int
    price: float


class OrderCreate(BaseModel):
    user_id: str
    items: List[OrderItem]


class Order(BaseModel):
    id: int
    user_id: str
    items: List[OrderItem]
    status: str
    total: float
    created_at: datetime


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "order-service"}


@app.get("/")
async def root():
    return {"service": "order-service", "version": "1.0.0"}


@app.post("/orders", response_model=Order, status_code=status.HTTP_201_CREATED)
async def create_order(order_data: OrderCreate):
    """Create a new order - validates user exists via User service"""
    global order_counter

    # Validate user exists by calling User service
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{USER_SERVICE_URL}/users/{order_data.user_id}")
            if response.status_code == 404:
                raise HTTPException(status_code=400, detail="User not found")
    except httpx.ConnectError:
        # User service might not be running, continue anyway in dev
        pass

    # Calculate total
    total = sum(item.quantity * item.price for item in order_data.items)

    order = Order(
        id=order_counter,
        user_id=order_data.user_id,
        items=order_data.items,
        status="pending",
        total=total,
        created_at=datetime.utcnow()
    )
    orders_db[order_counter] = order
    order_counter += 1

    return order


@app.get("/orders", response_model=List[Order])
async def list_orders(user_id: Optional[str] = None):
    """List orders, optionally filter by user_id"""
    orders = list(orders_db.values())
    if user_id:
        orders = [o for o in orders if o.user_id == user_id]
    return orders


@app.get("/orders/{order_id}", response_model=Order)
async def get_order(order_id: int):
    if order_id not in orders_db:
        raise HTTPException(status_code=404, detail="Order not found")
    return orders_db[order_id]


@app.patch("/orders/{order_id}/status")
async def update_order_status(order_id: int, status: str):
    """Update order status"""
    if order_id not in orders_db:
        raise HTTPException(status_code=404, detail="Order not found")

    valid_statuses = ["pending", "confirmed", "processing", "shipped", "delivered", "cancelled"]
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")

    orders_db[order_id].status = status
    return orders_db[order_id]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)