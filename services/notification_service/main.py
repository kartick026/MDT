"""
Notification Service
Handles sending notifications to users (email, SMS, push)
"""
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import uuid

app = FastAPI(title="Notification Service", version="1.0.0")

# In-memory storage
notifications_db = {}


class NotificationRequest(BaseModel):
    user_id: str
    type: str  # email, sms, push
    subject: Optional[str] = None
    message: str
    priority: str = "normal"  # low, normal, high, urgent


class Notification(BaseModel):
    id: str
    user_id: str
    type: str
    subject: Optional[str]
    message: str
    priority: str
    status: str  # pending, sent, delivered, failed
    created_at: datetime


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "notification-service"}


@app.get("/")
async def root():
    return {"service": "notification-service", "version": "1.0.0"}


@app.post("/notifications", response_model=Notification, status_code=status.HTTP_201_CREATED)
async def send_notification(notification_data: NotificationRequest):
    """Send a notification to a user"""
    notification_id = str(uuid.uuid4())[:8]

    notification = Notification(
        id=notification_id,
        user_id=notification_data.user_id,
        type=notification_data.type,
        subject=notification_data.subject,
        message=notification_data.message,
        priority=notification_data.priority,
        status="sent",  # Simplified - real would be async
        created_at=datetime.utcnow()
    )

    notifications_db[notification_id] = notification
    return notification


@app.get("/notifications", response_model=List[Notification])
async def list_notifications(user_id: Optional[str] = None):
    """List notifications, optionally filter by user"""
    notifications = list(notifications_db.values())
    if user_id:
        notifications = [n for n in notifications if n.user_id == user_id]
    return notifications


@app.get("/notifications/{notification_id}", response_model=Notification)
async def get_notification(notification_id: str):
    if notification_id not in notifications_db:
        raise HTTPException(status_code=404, detail="Notification not found")
    return notifications_db[notification_id]


@app.post("/notifications/order/{order_id}/confirmation")
async def send_order_confirmation(order_id: int, user_id: str):
    """Send order confirmation notification"""
    notification_id = str(uuid.uuid4())[:8]

    notification = Notification(
        id=notification_id,
        user_id=user_id,
        type="email",
        subject=f"Order #{order_id} Confirmed",
        message=f"Your order #{order_id} has been confirmed and is being processed.",
        priority="normal",
        status="sent",
        created_at=datetime.utcnow()
    )

    notifications_db[notification_id] = notification
    return notification


@app.post("/notifications/payment/{order_id}/receipt")
async def send_payment_receipt(order_id: int, user_id: str, amount: float):
    """Send payment receipt notification"""
    notification_id = str(uuid.uuid4())[:8]

    notification = Notification(
        id=notification_id,
        user_id=user_id,
        type="email",
        subject=f"Payment Received for Order #{order_id}",
        message=f"We have received your payment of ${amount:.2f} for order #{order_id}.",
        priority="normal",
        status="sent",
        created_at=datetime.utcnow()
    )

    notifications_db[notification_id] = notification
    return notification


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)