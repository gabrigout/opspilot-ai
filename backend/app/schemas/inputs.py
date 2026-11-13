"""Request bodies (validated by Pydantic)."""
import uuid
from typing import Literal

from pydantic import BaseModel, Field

from app.models.enums import CourierStatus, IncidentStatus, IncidentType, OrderStatus, Priority


class LoginIn(BaseModel):
    # Plain string (not EmailStr): reserved demo domains such as *.local are rejected by strict validators.
    email: str = Field(..., min_length=3, max_length=255, pattern=r"^[^@\s]+@[^@\s]+$")
    password: str = Field(..., min_length=1, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


class OrderStatusIn(BaseModel):
    status: OrderStatus
    reason: str | None = Field(None, max_length=200)


class AssignIn(BaseModel):
    courier_id: str = Field(..., min_length=1, max_length=64, description="UUID ou código (E-001)")


class CourierStatusIn(BaseModel):
    status: CourierStatus


class IncidentCreateIn(BaseModel):
    type: IncidentType
    priority: Priority = Priority.MEDIUM
    description: str = Field(..., min_length=5, max_length=2000)
    order_ref: str | None = Field(None, max_length=64, description="UUID ou código do pedido")
    title: str | None = Field(None, max_length=160)
    assignee: str | None = Field(None, max_length=120)


class IncidentUpdateIn(BaseModel):
    status: IncidentStatus | None = None
    priority: Priority | None = None
    assignee: str | None = Field(None, max_length=120)
    resolution: str | None = Field(None, max_length=2000)
    description: str | None = Field(None, min_length=5, max_length=2000)


class ChatIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    conversation_id: uuid.UUID | None = None


class ConfirmIn(BaseModel):
    approve: bool


class AdvanceIn(BaseModel):
    minutes: float = Field(..., gt=0, le=240)
    auto_assign: bool = Field(True, description="Regra explícita do simulador: atribuir o melhor candidato a pedidos aguardando entregador")


class SimActionIn(BaseModel):
    action: Literal["spawn_orders", "demand_spike", "reduce_couriers", "restore_couriers", "restaurant_delay",
                    "cancel_orders", "generate_incidents"]
    count: int = Field(5, ge=1, le=60)
    restaurant: str | None = Field(None, max_length=80)
    factor: float = Field(1.8, ge=0.5, le=4.0)
