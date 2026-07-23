"""
Payment Service
Handles payment processing for orders
"""
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uuid
import httpx

app = FastAPI(title="Payment Service", version="1.0.0")

# In-memory storage
payments_db = {}

# Service URLs
ORDER_SERVICE_URL = "http://order-service:8002"


class PaymentRequest(BaseModel):
    order_id: int
    amount: float
    method: str  # credit_card, debit_card, paypal, etc.
    card_last_four: Optional[str] = None


class Payment(BaseModel):
    id: str
    order_id: int
    amount: float
    method: str
    status: str
    created_at: datetime


class PaymentStatus(BaseModel):
    status: str
    payment_id: str


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "payment-service"}


@app.get("/")
async def root():
    return {"service": "payment-service", "version": "1.0.0"}


@app.post("/payments", response_model=Payment, status_code=status.HTTP_201_CREATED)
async def create_payment(payment_data: PaymentRequest):
    """
    Process a payment for an order.
    In production, this would integrate with Stripe/PayPal/etc.
    """
    # Validate order exists
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{ORDER_SERVICE_URL}/orders/{payment_data.order_id}")
            if response.status_code == 404:
                raise HTTPException(status_code=400, detail="Order not found")
    except httpx.ConnectError:
        pass  # Allow in dev if order service is down

    payment_id = str(uuid.uuid4())[:8]

    payment = Payment(
        id=payment_id,
        order_id=payment_data.order_id,
        amount=payment_data.amount,
        method=payment_data.method,
        status="completed",  # Simplified - real would be async
        created_at=datetime.utcnow()
    )

    payments_db[payment_id] = payment
    return payment


@app.get("/payments/{payment_id}", response_model=Payment)
async def get_payment(payment_id: str):
    if payment_id not in payments_db:
        raise HTTPException(status_code=404, detail="Payment not found")
    return payments_db[payment_id]


@app.post("/payments/{payment_id}/refund", response_model=PaymentStatus)
async def refund_payment(payment_id: str):
    """Process a refund for an existing payment"""
    if payment_id not in payments_db:
        raise HTTPException(status_code=404, detail="Payment not found")

    payment = payments_db[payment_id]
    payment.status = "refunded"

    return PaymentStatus(status="refunded", payment_id=payment_id)


@app.get("/payments/order/{order_id}")
async def get_payment_by_order(order_id: int):
    """Get payment for a specific order"""
    for payment in payments_db.values():
        if payment.order_id == order_id:
            return payment
    raise HTTPException(status_code=404, detail="Payment not found for this order")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)