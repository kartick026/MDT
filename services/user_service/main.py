"""
User Service
Handles user management operations
"""
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime
import uuid

app = FastAPI(title="User Service", version="1.0.0")

# In-memory database for demo
users_db = {}


class User(BaseModel):
    id: str
    email: EmailStr
    name: str
    created_at: datetime


class UserCreate(BaseModel):
    email: EmailStr
    name: str


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    name: Optional[str] = None


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "user-service"}


@app.get("/")
async def root():
    return {"service": "user-service", "version": "1.0.0"}


@app.post("/users", response_model=User, status_code=status.HTTP_201_CREATED)
async def create_user(user_data: UserCreate):
    """Create a new user"""
    user_id = str(uuid.uuid4())
    user = User(
        id=user_id,
        email=user_data.email,
        name=user_data.name,
        created_at=datetime.utcnow()
    )
    users_db[user_id] = user
    return user


@app.get("/users", response_model=List[User])
async def list_users():
    """List all users"""
    return list(users_db.values())


@app.get("/users/{user_id}", response_model=User)
async def get_user(user_id: str):
    """Get user by ID"""
    if user_id not in users_db:
        raise HTTPException(status_code=404, detail="User not found")
    return users_db[user_id]


@app.put("/users/{user_id}", response_model=User)
async def update_user(user_id: str, user_data: UserUpdate):
    """Update user information"""
    if user_id not in users_db:
        raise HTTPException(status_code=404, detail="User not found")

    user = users_db[user_id]
    if user_data.email:
        user.email = user_data.email
    if user_data.name:
        user.name = user_data.name

    return user


@app.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: str):
    """Delete a user"""
    if user_id not in users_db:
        raise HTTPException(status_code=404, detail="User not found")
    del users_db[user_id]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)