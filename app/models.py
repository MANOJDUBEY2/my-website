


# 🐾 PawVibe – Phase 2: Backend Core (FastAPI)


## **6. backend/app/models.py**


"""
models.py – SQLAlchemy ORM Models for PawVibe
─────────────────────────────────────────────
Defines all database tables as Python classes.
Each model maps 1:1 to a SQLite table managed by Alembic migrations.

Tables:
  - User           → customers and admins
  - Product        → dropshipping catalog
  - CartItem       → per-user shopping cart rows
  - WishlistItem   → per-user wishlist rows
  - Order          → placed orders
  - OrderItem      → line items within an order
"""

from datetime import datetime
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from .database import Base


# ─────────────────────────────────────────────────────────────────────────────
# User Model
# ─────────────────────────────────────────────────────────────────────────────
class User(Base):
    """
    Represents a registered user (customer or admin).
    loyalty_points accumulate with each order (1 point per ₹10 spent).
    """
    __tablename__ = "users"

    id            = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name          = Column(String(100), nullable=False)
    email         = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(200), nullable=False)
    role          = Column(String(20), default="customer", nullable=False)
    # Loyalty programme: points earned = floor(total_spent / 10)
    loyalty_points = Column(Integer, default=0, nullable=False)
    is_active     = Column(Boolean, default=True, nullable=False)
    created_at    = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships — lazy loaded by default; use joinedload for performance
    cart_items    = relationship(
        "CartItem",
        back_populates="user",
        cascade="all, delete-orphan",   # deleting user removes their cart
    )
    wishlist_items = relationship(
        "WishlistItem",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    orders        = relationship(
        "Order",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} role={self.role!r}>"


# ─────────────────────────────────────────────────────────────────────────────
# Product Model
# ─────────────────────────────────────────────────────────────────────────────
class Product(Base):
    """
    Represents a dropshipping product in the catalog.

    price      → what the customer pays (selling price in INR)
    cost_price → what we pay the supplier (for margin calculation)
    badges     → comma-separated tags e.g. "bestseller,new,hot"
    stock      → defaults to 999 for dropshipping (virtual inventory)
    """
    __tablename__ = "products"

    id           = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name         = Column(String(200), nullable=False, index=True)
    # URL-friendly slug for SEO e.g. "cooling-mat-for-dogs"
    slug         = Column(String(200), unique=True, index=True, nullable=False)
    # Category: 'dog' | 'cat' | 'both'
    category     = Column(String(50), nullable=False, index=True)
    price        = Column(Float, nullable=False)
    cost_price   = Column(Float, nullable=False)
    image_url    = Column(String(500), nullable=False)
    description  = Column(Text, nullable=True)
    # Comma-separated badge string: 'bestseller', 'new', 'hot', 'trending'
    badges       = Column(String(200), default="", nullable=True)
    # Virtual stock for dropshipping (effectively unlimited)
    stock        = Column(Integer, default=999, nullable=False)
    # Aggregate rating (updated on review submission)
    rating       = Column(Float, default=4.5, nullable=False)
    review_count = Column(Integer, default=0, nullable=False)
    is_active    = Column(Boolean, default=True, nullable=False)
    created_at   = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    cart_items      = relationship("CartItem", back_populates="product")
    wishlist_items  = relationship("WishlistItem", back_populates="product")
    order_items     = relationship("OrderItem", back_populates="product")

    @property
    def margin_inr(self) -> float:
        """Calculate profit margin in INR."""
        return round(self.price - self.cost_price, 2)

    @property
    def margin_percent(self) -> float:
        """Calculate profit margin as a percentage of selling price."""
        if self.price == 0:
            return 0.0
        return round((self.margin_inr / self.price) * 100, 1)

    def __repr__(self) -> str:
        return f"<Product id={self.id} name={self.name!r} price=₹{self.price}>"


# ─────────────────────────────────────────────────────────────────────────────
# Cart Item Model
# ─────────────────────────────────────────────────────────────────────────────
class CartItem(Base):
    """
    A single product line in a user's shopping cart.
    One row per (user_id, product_id) pair — quantity is updated in-place.
    """
    __tablename__ = "cart_items"

    id         = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id    = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    quantity   = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user    = relationship("User", back_populates="cart_items")
    product = relationship("Product", back_populates="cart_items")

    def __repr__(self) -> str:
        return f"<CartItem user={self.user_id} product={self.product_id} qty={self.quantity}>"


# ─────────────────────────────────────────────────────────────────────────────
# Wishlist Item Model
# ─────────────────────────────────────────────────────────────────────────────
class WishlistItem(Base):
    """
    A product saved to a user's wishlist.
    Toggle endpoint adds or removes based on existence.
    """
    __tablename__ = "wishlist_items"

    id         = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id    = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user    = relationship("User", back_populates="wishlist_items")
    product = relationship("Product", back_populates="wishlist_items")

    def __repr__(self) -> str:
        return f"<WishlistItem user={self.user_id} product={self.product_id}>"


# ─────────────────────────────────────────────────────────────────────────────
# Order Model
# ─────────────────────────────────────────────────────────────────────────────
class Order(Base):
    """
    Represents a placed order.

    status lifecycle:
      pending → processing → shipped → out_for_delivery → delivered
                                 ↘ (cancelled)

    supplier_forwarded:
      False → order not yet forwarded to dropshipping supplier
      True  → admin has forwarded, supplier is fulfilling
    """
    __tablename__ = "orders"

    id                 = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id            = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    total_amount       = Column(Float, nullable=False)
    status             = Column(String(50), default="pending", nullable=False)
    # Has this order been forwarded to the dropshipping supplier?
    supplier_forwarded = Column(Boolean, default=False, nullable=False)
    # Shipping address stored as a JSON string for flexibility
    shipping_address   = Column(Text, nullable=True)
    payment_method     = Column(String(50), default="upi", nullable=False)
    # Mock tracking ID (generated on supplier forward)
    tracking_id        = Column(String(100), nullable=True)
    created_at         = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user        = relationship("User", back_populates="orders")
    order_items = relationship(
        "OrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Order id={self.id} user={self.user_id} total=₹{self.total_amount} status={self.status!r}>"


# ─────────────────────────────────────────────────────────────────────────────
# Order Item Model
# ─────────────────────────────────────────────────────────────────────────────
class OrderItem(Base):
    """
    A single product line within an Order.
    unit_price is snapshotted at purchase time (price may change later).
    """
    __tablename__ = "order_items"

    id         = Column(Integer, primary_key=True, index=True, autoincrement=True)
    order_id   = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    quantity   = Column(Integer, nullable=False)
    # Price snapshot — what the customer actually paid per unit
    unit_price = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    order   = relationship("Order", back_populates="order_items")
    product = relationship("Product", back_populates="order_items")

    @property
    def subtotal(self) -> float:
        """Line-level subtotal."""
        return round(self.unit_price * self.quantity, 2)

    def __repr__(self) -> str:
        return f"<OrderItem order={self.order_id} product={self.product_id} qty={self.quantity}>"
