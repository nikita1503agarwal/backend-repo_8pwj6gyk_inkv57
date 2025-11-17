from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class ProductIn(BaseModel):
    name: str
    brand: str
    category: str
    price: float
    sale_price: Optional[float] = None
    stock: int = 0
    description: Optional[str] = None
    images: List[str] = Field(default_factory=list)
    specs: Optional[Dict[str, Any]] = None
    options: Optional[Dict[str, Any]] = None
    is_featured: bool = False
    tags: List[str] = Field(default_factory=list)
    rating: Optional[float] = 0.0


class ProductOut(ProductIn):
    id: str
    created_at: datetime
    updated_at: datetime


class ShippingInfo(BaseModel):
    full_name: str
    email: str
    phone: str
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    method: str  # 'home_delivery' | 'store_pickup' | 'express'


class PaymentInfo(BaseModel):
    method: str  # 'card' | 'cod' | 'wallet'
    status: str = 'pending'
    transaction_id: Optional[str] = None


class OrderItem(BaseModel):
    product_id: str
    name: str
    price: float
    quantity: int
    image: Optional[str] = None
    selected_options: Optional[Dict[str, Any]] = None


class OrderIn(BaseModel):
    items: List[OrderItem]
    shipping: ShippingInfo
    payment: PaymentInfo
    subtotal: float
    shipping_cost: float
    discount: float = 0.0
    total: float


class OrderOut(OrderIn):
    id: str
    status: str
    created_at: datetime
    updated_at: datetime
