"""Core operational entities: users, restaurants, customers, orders, couriers."""
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, Enum, Float, ForeignKey, Index, Integer, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, UTCDateTime
from app.models.enums import CourierStatus, OrderStatus, RestaurantStatus, UserRole


def _enum(e):
    return Enum(e, native_enum=False, length=32, validate_strings=True, create_constraint=True)


def _uuid():
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = _uuid()
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(_enum(UserRole), default=UserRole.VIEWER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class Restaurant(Base):
    __tablename__ = "restaurants"
    id: Mapped[uuid.UUID] = _uuid()
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(60))
    address: Mapped[str] = mapped_column(String(200))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    status: Mapped[RestaurantStatus] = mapped_column(_enum(RestaurantStatus), default=RestaurantStatus.OPEN)
    avg_prep_minutes: Mapped[float] = mapped_column(Float)  # nominal baseline
    rating: Mapped[float] = mapped_column(Float, default=4.5)
    delay_factor: Mapped[float] = mapped_column(Float, default=1.0)  # simulation lever
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    orders: Mapped[list["Order"]] = relationship(back_populates="restaurant")


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[uuid.UUID] = _uuid()
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(30))
    address: Mapped[str] = mapped_column(String(200))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)


class Courier(Base):
    __tablename__ = "couriers"
    id: Mapped[uuid.UUID] = _uuid()
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    status: Mapped[CourierStatus] = mapped_column(_enum(CourierStatus), default=CourierStatus.AVAILABLE, index=True)
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    total_deliveries: Mapped[int] = mapped_column(Integer, default=0)
    avg_delivery_minutes: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)
    orders: Mapped[list["Order"]] = relationship(back_populates="courier")


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_status_created", "status", "created_at"),
        Index("ix_orders_restaurant_created", "restaurant_id", "created_at"),
    )
    id: Mapped[uuid.UUID] = _uuid()
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    restaurant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("restaurants.id"), index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id"))
    courier_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("couriers.id"), index=True, nullable=True)
    status: Mapped[OrderStatus] = mapped_column(_enum(OrderStatus), default=OrderStatus.RECEIVED)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    est_prep_minutes: Mapped[int] = mapped_column(Integer)
    est_delivery_minutes: Mapped[int] = mapped_column(Integer)  # promised total time
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    promised_at: Mapped[datetime] = mapped_column(UTCDateTime)
    ready_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    picked_up_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)
    # Simulation: how long this order will really take (drives `advance`).
    sim_prep_minutes: Mapped[float] = mapped_column(Float)
    sim_travel_minutes: Mapped[float] = mapped_column(Float)

    restaurant: Mapped[Restaurant] = relationship(back_populates="orders")
    customer: Mapped[Customer] = relationship()
    courier: Mapped[Courier | None] = relationship(back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    events: Mapped[list["OrderEvent"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="OrderEvent.created_at"
    )


class OrderItem(Base):
    __tablename__ = "order_items"
    id: Mapped[uuid.UUID] = _uuid()
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    order: Mapped[Order] = relationship(back_populates="items")


class OrderEvent(Base):
    __tablename__ = "order_events"
    id: Mapped[uuid.UUID] = _uuid()
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(40))
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(80), default="system")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    order: Mapped[Order] = relationship(back_populates="events")
