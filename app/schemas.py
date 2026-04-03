"""
schemas.py – Pydantic v2 Schemas for PawVibe
─────────────────────────────────────────────
Defines all request/response shapes for the REST API.

Naming convention:
  <Model>Base     → shared fields
  <Model>Create   → fields required on creation (input)
  <Model>Update   → optional fields for partial updates (PATCH-style)
  <Model>Response → fields returned to the client (output)
  <Model>Public   → publicly visible subset (e.g., no cost_price)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


# ─────────────────────────────────────────────────────────────────────────────
# Generic API Response Wrapper
# ─────────────────────────────────────────────────────────────────────────────
class APIResponse(BaseModel):
    """Standard envelope for all API responses."""
    success: bool = True
    data: Any = None
    message: str = "OK"


class PaginatedResponse(BaseModel):
    """Pagination metadata wrapper."""
    items: List[Any]
    total: int
    page: int
    per_page: int
    pages: int


# ─────────────────────────────────────────────────────────────────────────────
# Auth Schemas
# ─────────────────────────────────────────────────────────────────────────────
class UserRegister(BaseModel):
    """Payload for POST /api/v1/auth/register"""
    name:     str      = Field(..., min_length=2, max_length=100, examples=["Priya Sharma"])
    email:    EmailStr = Field(..., examples=["priya@example.com"])
    password: str      = Field(..., min_length=8, max_length=128, examples=["SecurePass@123"])

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        """Ensure password has at least one digit and one letter."""
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit.")
        if not any(c.isalpha() for c in v):
            raise ValueError("Password must contain at least one letter.")
        return v

    @field_validator("name")
    @classmethod
    def name_no_numbers(cls, v: str) -> str:
        """Strip extra whitespace from name."""
        return v.strip()


class UserLogin(BaseModel):
    """Payload for POST /api/v1/auth/login"""
    email:    EmailStr = Field(..., examples=["priya@example.com"])
    password: str      = Field(..., examples=["SecurePass@123"])


class TokenRefresh(BaseModel):
    """Payload for POST /api/v1/auth/refresh"""
    refresh_token: str


class TokenResponse(BaseModel):
    """Returned tokens after login or refresh."""
    access_token:  str
    refresh_token: str
    token_type:    str = "bearer"


# ─────────────────────────────────────────────────────────────────────────────
# User Schemas
# ─────────────────────────────────────────────────────────────────────────────
class UserBase(BaseModel):
    name:  str
    email: EmailStr


class UserResponse(UserBase):
    """Safe user object returned to clients (no password)."""
    id:             int
    role:           str
    loyalty_points: int
    is_active:      bool
    created_at:     datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    """Fields a user can update on their own profile."""
    name:     Optional[str] = Field(None, min_length=2, max_length=100)
    password: Optional[str] = Field(None, min_length=8, max_length=128)


# ─────────────────────────────────────────────────────────────────────────────
# Product Schemas
# ─────────────────────────────────────────────────────────────────────────────
class ProductBase(BaseModel):
    name:        str   = Field(..., min_length=3, max_length=200)
    category:    str   = Field(..., pattern="^(dog|cat|both)$")
    price:       float = Field(..., gt=0, description="Selling price in INR")
    cost_price:  float = Field(..., gt=0, description="Supplier cost in INR")
    image_url:   str   = Field(..., min_length=10)
    description: Optional[str] = None
    badges:      Optional[str] = ""   # e.g. "bestseller,new"
    stock:       int   = Field(default=999, ge=0)


class ProductCreate(ProductBase):
    """Payload for POST /api/v1/products (admin only)."""
    slug: Optional[str] = None   # Auto-generated from name if not provided

    @field_validator("slug", mode="before")
    @classmethod
    def slugify_name(cls, v: Optional[str], info: Any) -> str:
        """Auto-generate slug from name if not explicitly provided."""
        if v:
            return v.lower().replace(" ", "-")
        # Access the 'name' field from the data being validated
        name = info.data.get("name", "")
        return name.lower().replace(" ", "-").replace("/", "-")


class ProductUpdate(BaseModel):
    """Partial update payload for PUT /api/v1/products/{id}."""
    name:        Optional[str]   = None
    category:    Optional[str]   = Field(None, pattern="^(dog|cat|both)$")
    price:       Optional[float] = Field(None, gt=0)
    cost_price:  Optional[float] = Field(None, gt=0)
    image_url:   Optional[str]   = None
    description: Optional[str]   = None
    badges:      Optional[str]   = None
    stock:       Optional[int]   = Field(None, ge=0)
    is_active:   Optional[bool]  = None


class ProductPublic(BaseModel):
    """
    Product shape returned to all clients.
    Note: cost_price is EXCLUDED for security (margin visibility).
    margin_inr and margin_percent included for admin only (see ProductAdmin).
    """
    id:           int
    name:         str
    slug:         str
    category:     str
    price:        float
    image_url:    str
    description:  Optional[str]
    badges:       Optional[str]
    stock:        int
    rating:       float
    review_count: int
    is_active:    bool
    created_at:   datetime

    model_config = {"from_attributes": True}


class ProductAdmin(ProductPublic):
    """Extended product response for admin users — includes cost + margins."""
    cost_price:     float
    margin_inr:     float
    margin_percent: float

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# Cart Schemas
# ─────────────────────────────────────────────────────────────────────────────
class CartItemAdd(BaseModel):
    """Payload for POST /api/v1/cart/add"""
    product_id: int = Field(..., gt=0)
    quantity:   int = Field(default=1, ge=1, le=10)


class CartItemUpdate(BaseModel):
    """Payload for PUT /api/v1/cart/update/{item_id}"""
    quantity: int = Field(..., ge=1, le=10)


class CartItemResponse(BaseModel):
    """A single cart item with embedded product details."""
    id:         int
    product_id: int
    quantity:   int
    # Embedded product fields for display (no extra API call needed)
    product_name:  str
    product_image: str
    unit_price:    float
    subtotal:      float
    created_at:    datetime

    model_config = {"from_attributes": True}


class CartResponse(BaseModel):
    """Full cart state returned to the client."""
    items:           List[CartItemResponse]
    total:           float
    item_count:      int
    # Shipping threshold info
    free_shipping_threshold: float = 599.0
    amount_for_free_shipping: float


# ─────────────────────────────────────────────────────────────────────────────
# Wishlist Schemas
# ─────────────────────────────────────────────────────────────────────────────
class WishlistToggle(BaseModel):
    """Payload for POST /api/v1/wishlist/toggle"""
    product_id: int = Field(..., gt=0)


class WishlistItemResponse(BaseModel):
    """A single wishlist item with embedded product details."""
    id:         int
    product_id: int
    product:    ProductPublic
    created_at: datetime

    model_config = {"from_attributes": True}


class WishlistResponse(BaseModel):
    """Full wishlist state."""
    items:      List[WishlistItemResponse]
    item_count: int
    # Was the last toggle operation an "add" or "remove"?
    action:     Optional[str] = None   # 'added' | 'removed'


# ─────────────────────────────────────────────────────────────────────────────
# Order Schemas
# ─────────────────────────────────────────────────────────────────────────────
class ShippingAddress(BaseModel):
    """Embedded shipping address within an order."""
    full_name:   str = Field(..., min_length=2)
    phone:       str = Field(..., min_length=10, max_length=15)
    address_line1: str = Field(..., min_length=5)
    address_line2: Optional[str] = None
    city:        str = Field(..., min_length=2)
    state:       str = Field(..., min_length=2)
    pincode:     str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")

    @field_validator("phone")
    @classmethod
    def validate_indian_phone(cls, v: str) -> str:
        digits = "".join(c for c in v if c.isdigit())
        if len(digits) < 10:
            raise ValueError("Phone number must have at least 10 digits.")
        return v


class OrderItemCreate(BaseModel):
    """A line item in an order creation payload."""
    product_id: int
    quantity:   int = Field(..., ge=1)


class OrderCreate(BaseModel):
    """Payload for POST /api/v1/orders"""
    items:           List[OrderItemCreate] = Field(..., min_length=1)
    shipping_address: ShippingAddress
    payment_method:  str = Field(default="upi", pattern="^(upi|card|cod|netbanking)$")

    @field_validator("items")
    @classmethod
    def items_not_empty(cls, v: List[OrderItemCreate]) -> List[OrderItemCreate]:
        if not v:
            raise ValueError("Order must contain at least one item.")
        return v


class OrderItemResponse(BaseModel):
    """Order line item with product snapshot."""
    id:           int
    product_id:   int
    product_name: str
    product_image: str
    quantity:     int
    unit_price:   float
    subtotal:     float

    model_config = {"from_attributes": True}


class OrderResponse(BaseModel):
    """Full order object returned to clients."""
    id:                 int
    user_id:            int
    total_amount:       float
    status:             str
    supplier_forwarded: bool
    shipping_address:   Optional[str]   # JSON string
    payment_method:     str
    tracking_id:        Optional[str]
    items:              List[OrderItemResponse]
    created_at:         datetime

    model_config = {"from_attributes": True}


class OrderStatusUpdate(BaseModel):
    """Admin payload for updating order status."""
    status: str = Field(..., pattern="^(pending|processing|shipped|out_for_delivery|delivered|cancelled)$")


class OrderForwardResponse(BaseModel):
    """Response after marking an order as forwarded to supplier."""
    order_id:           int
    supplier_forwarded: bool
    tracking_id:        str
    message:            str


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard / Analytics Schemas (Admin)
# ─────────────────────────────────────────────────────────────────────────────
class DashboardStats(BaseModel):
    """Quick stats for the admin dashboard."""
    total_orders:        int
    pending_orders:      int
    total_revenue:       float
    total_products:      int
    total_users:         int
    orders_not_forwarded: int
