"""
crud.py – Database Operations for PawVibe
─────────────────────────────────────────
All database reads/writes live here.
Routes call these functions — never query the DB directly in routes.

Organisation:
  - CRUD_User
  - CRUD_Product
  - CRUD_Cart
  - CRUD_Wishlist
  - CRUD_Order
  - CRUD_Admin (stats, bulk ops)
"""

import json
import math
import random
import string
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from . import models, schemas
from .auth import get_password_hash, verify_password


# ═════════════════════════════════════════════════════════════════════════════
# Helper Utilities
# ═════════════════════════════════════════════════════════════════════════════

def _generate_tracking_id() -> str:
    """Generate a mock tracking ID like PV-MUM-20260401-XKQM."""
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    date_str = datetime.utcnow().strftime("%Y%m%d")
    cities = ["MUM", "DEL", "BLR", "HYD", "CHE", "KOL", "PUN"]
    city = random.choice(cities)
    return f"PV-{city}-{date_str}-{suffix}"


def _slugify(text: str) -> str:
    """Convert a product name to a URL-safe slug."""
    return (
        text.lower()
        .replace(" ", "-")
        .replace("/", "-")
        .replace("(", "")
        .replace(")", "")
        .replace(",", "")
        .replace("'", "")
        .strip("-")
    )


# ═════════════════════════════════════════════════════════════════════════════
# USER CRUD
# ═════════════════════════════════════════════════════════════════════════════

def get_user_by_id(db: Session, user_id: int) -> Optional[models.User]:
    """Fetch a user by primary key."""
    return db.query(models.User).filter(models.User.id == user_id).first()


def get_user_by_email(db: Session, email: str) -> Optional[models.User]:
    """Fetch a user by email address (used for login)."""
    return db.query(models.User).filter(
        func.lower(models.User.email) == email.lower()
    ).first()


def create_user(db: Session, payload: schemas.UserRegister, role: str = "customer") -> models.User:
    """
    Create a new user account.
    Password is hashed before storage.
    """
    user = models.User(
        name=payload.name.strip(),
        email=payload.email.lower().strip(),
        hashed_password=get_password_hash(payload.password),
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> Optional[models.User]:
    """
    Verify login credentials.
    Returns the User if credentials match, None otherwise.
    """
    user = get_user_by_email(db, email)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    if not user.is_active:
        return None
    return user


def update_user(db: Session, user: models.User, payload: schemas.UserUpdate) -> models.User:
    """Update a user's name and/or password."""
    if payload.name is not None:
        user.name = payload.name.strip()
    if payload.password is not None:
        user.hashed_password = get_password_hash(payload.password)
    db.commit()
    db.refresh(user)
    return user


def add_loyalty_points(db: Session, user: models.User, order_total: float) -> int:
    """
    Award loyalty points: 1 point per ₹10 spent.
    Returns the points awarded this transaction.
    """
    points_earned = int(order_total // 10)
    user.loyalty_points += points_earned
    db.commit()
    return points_earned


def get_all_users(db: Session, skip: int = 0, limit: int = 50) -> List[models.User]:
    """Admin: list all users with pagination."""
    return db.query(models.User).offset(skip).limit(limit).all()


# ═════════════════════════════════════════════════════════════════════════════
# PRODUCT CRUD
# ═════════════════════════════════════════════════════════════════════════════

def get_product_by_id(db: Session, product_id: int) -> Optional[models.Product]:
    """Fetch a single product by ID."""
    return db.query(models.Product).filter(
        models.Product.id == product_id,
        models.Product.is_active == True,
    ).first()


def get_product_by_slug(db: Session, slug: str) -> Optional[models.Product]:
    """Fetch a single product by URL slug."""
    return db.query(models.Product).filter(
        models.Product.slug == slug,
        models.Product.is_active == True,
    ).first()


def get_products(
    db: Session,
    category: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    badge: Optional[str] = None,
    search: Optional[str] = None,
    sort: str = "created_at_desc",
    page: int = 1,
    per_page: int = 12,
) -> Tuple[List[models.Product], int]:
    """
    Fetch products with filtering, searching, sorting, and pagination.
    Returns (list_of_products, total_count).
    """
    query = db.query(models.Product).filter(models.Product.is_active == True)

    # ── Category filter ───────────────────────────────────────────────────────
    if category and category in ("dog", "cat"):
        query = query.filter(
            or_(models.Product.category == category, models.Product.category == "both")
        )

    # ── Price range filter ────────────────────────────────────────────────────
    if min_price is not None:
        query = query.filter(models.Product.price >= min_price)
    if max_price is not None:
        query = query.filter(models.Product.price <= max_price)

    # ── Badge filter (comma-separated in DB) ─────────────────────────────────
    if badge:
        query = query.filter(models.Product.badges.like(f"%{badge}%"))

    # ── Full-text search on name and description ──────────────────────────────
    if search:
        search_term = f"%{search.lower()}%"
        query = query.filter(
            or_(
                func.lower(models.Product.name).like(search_term),
                func.lower(models.Product.description).like(search_term),
            )
        )

    # ── Total count before pagination ─────────────────────────────────────────
    total = query.count()

    # ── Sorting ───────────────────────────────────────────────────────────────
    sort_map = {
        "price_asc":       models.Product.price.asc(),
        "price_desc":      models.Product.price.desc(),
        "rating_desc":     models.Product.rating.desc(),
        "created_at_desc": models.Product.created_at.desc(),
        "name_asc":        models.Product.name.asc(),
    }
    order_clause = sort_map.get(sort, models.Product.created_at.desc())
    query = query.order_by(order_clause)

    # ── Pagination ────────────────────────────────────────────────────────────
    offset = (page - 1) * per_page
    products = query.offset(offset).limit(per_page).all()

    return products, total


def create_product(db: Session, payload: schemas.ProductCreate) -> models.Product:
    """Create a new product in the catalog."""
    slug = payload.slug or _slugify(payload.name)

    # Ensure slug uniqueness by appending a number if needed
    base_slug = slug
    counter = 1
    while db.query(models.Product).filter(models.Product.slug == slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1

    product = models.Product(
        name=payload.name,
        slug=slug,
        category=payload.category,
        price=payload.price,
        cost_price=payload.cost_price,
        image_url=payload.image_url,
        description=payload.description,
        badges=payload.badges or "",
        stock=payload.stock,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def update_product(
    db: Session, product: models.Product, payload: schemas.ProductUpdate
) -> models.Product:
    """Partially update a product (admin only)."""
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(product, field, value)
    db.commit()
    db.refresh(product)
    return product


def delete_product(db: Session, product: models.Product) -> None:
    """Soft-delete a product by marking it inactive."""
    product.is_active = False
    db.commit()


def get_bestsellers(db: Session, limit: int = 6) -> List[models.Product]:
    """Return products tagged as 'bestseller', sorted by rating."""
    return (
        db.query(models.Product)
        .filter(
            models.Product.is_active == True,
            models.Product.badges.like("%bestseller%"),
        )
        .order_by(models.Product.rating.desc())
        .limit(limit)
        .all()
    )


def get_trending_products(db: Session, limit: int = 8) -> List[models.Product]:
    """Return products tagged as 'trending', newest first."""
    return (
        db.query(models.Product)
        .filter(
            models.Product.is_active == True,
            models.Product.badges.like("%trending%"),
        )
        .order_by(models.Product.created_at.desc())
        .limit(limit)
        .all()
    )


def get_related_products(
    db: Session, product: models.Product, limit: int = 4
) -> List[models.Product]:
    """Return products in the same category, excluding the current product."""
    return (
        db.query(models.Product)
        .filter(
            models.Product.is_active == True,
            models.Product.id != product.id,
            or_(
                models.Product.category == product.category,
                models.Product.category == "both",
            ),
        )
        .order_by(func.random())
        .limit(limit)
        .all()
    )


# ═════════════════════════════════════════════════════════════════════════════
# CART CRUD
# ═════════════════════════════════════════════════════════════════════════════

FREE_SHIPPING_THRESHOLD = 599.0   # INR — orders above this get free shipping


def _compute_cart_response(db: Session, user_id: int) -> schemas.CartResponse:
    """
    Build the full CartResponse for a user.
    Joins cart_items with products for display data.
    """
    cart_items = (
        db.query(models.CartItem)
        .options(joinedload(models.CartItem.product))
        .filter(models.CartItem.user_id == user_id)
        .all()
    )

    response_items: List[schemas.CartItemResponse] = []
    total = 0.0

    for item in cart_items:
        if item.product and item.product.is_active:
            subtotal = round(item.product.price * item.quantity, 2)
            total += subtotal
            response_items.append(
                schemas.CartItemResponse(
                    id=item.id,
                    product_id=item.product_id,
                    quantity=item.quantity,
                    product_name=item.product.name,
                    product_image=item.product.image_url,
                    unit_price=item.product.price,
                    subtotal=subtotal,
                    created_at=item.created_at,
                )
            )

    total = round(total, 2)
    item_count = sum(i.quantity for i in cart_items)
    amount_for_free = max(0.0, round(FREE_SHIPPING_THRESHOLD - total, 2))

    return schemas.CartResponse(
        items=response_items,
        total=total,
        item_count=item_count,
        free_shipping_threshold=FREE_SHIPPING_THRESHOLD,
        amount_for_free_shipping=amount_for_free,
    )


def get_cart(db: Session, user_id: int) -> schemas.CartResponse:
    """Return the current cart for a user."""
    return _compute_cart_response(db, user_id)


def add_to_cart(
    db: Session, user_id: int, payload: schemas.CartItemAdd
) -> schemas.CartResponse:
    """
    Add a product to the cart or increment its quantity.
    If the product is already in the cart, quantity is increased.
    """
    # Verify product exists
    product = get_product_by_id(db, payload.product_id)
    if not product:
        raise ValueError(f"Product {payload.product_id} not found.")

    # Check if already in cart
    existing = (
        db.query(models.CartItem)
        .filter(
            models.CartItem.user_id == user_id,
            models.CartItem.product_id == payload.product_id,
        )
        .first()
    )

    if existing:
        # Increment quantity (cap at 10 per item)
        existing.quantity = min(existing.quantity + payload.quantity, 10)
    else:
        # Create new cart item
        new_item = models.CartItem(
            user_id=user_id,
            product_id=payload.product_id,
            quantity=payload.quantity,
        )
        db.add(new_item)

    db.commit()
    return _compute_cart_response(db, user_id)


def update_cart_item(
    db: Session, user_id: int, item_id: int, payload: schemas.CartItemUpdate
) -> schemas.CartResponse:
    """Update the quantity of a specific cart item."""
    item = (
        db.query(models.CartItem)
        .filter(
            models.CartItem.id == item_id,
            models.CartItem.user_id == user_id,  # Ensure ownership
        )
        .first()
    )
    if not item:
        raise ValueError(f"Cart item {item_id} not found.")

    item.quantity = payload.quantity
    db.commit()
    return _compute_cart_response(db, user_id)


def remove_from_cart(db: Session, user_id: int, item_id: int) -> schemas.CartResponse:
    """Remove a specific item from the cart."""
    item = (
        db.query(models.CartItem)
        .filter(
            models.CartItem.id == item_id,
            models.CartItem.user_id == user_id,
        )
        .first()
    )
    if item:
        db.delete(item)
        db.commit()
    return _compute_cart_response(db, user_id)


def clear_cart(db: Session, user_id: int) -> None:
    """Remove all items from a user's cart (called after order placement)."""
    db.query(models.CartItem).filter(models.CartItem.user_id == user_id).delete()
    db.commit()


# ═════════════════════════════════════════════════════════════════════════════
# WISHLIST CRUD
# ═════════════════════════════════════════════════════════════════════════════

def get_wishlist(db: Session, user_id: int) -> schemas.WishlistResponse:
    """Return the full wishlist for a user with embedded product data."""
    items = (
        db.query(models.WishlistItem)
        .options(joinedload(models.WishlistItem.product))
        .filter(models.WishlistItem.user_id == user_id)
        .order_by(models.WishlistItem.created_at.desc())
        .all()
    )

    response_items = [
        schemas.WishlistItemResponse(
            id=item.id,
            product_id=item.product_id,
            product=schemas.ProductPublic.model_validate(item.product),
            created_at=item.created_at,
        )
        for item in items
        if item.product and item.product.is_active
    ]

    return schemas.WishlistResponse(
        items=response_items,
        item_count=len(response_items),
    )


def toggle_wishlist(
    db: Session, user_id: int, payload: schemas.WishlistToggle
) -> schemas.WishlistResponse:
    """
    Toggle a product in the wishlist.
    If it exists → remove it (action='removed')
    If it doesn't exist → add it (action='added')
    """
    # Verify product exists
    product = get_product_by_id(db, payload.product_id)
    if not product:
        raise ValueError(f"Product {payload.product_id} not found.")

    existing = (
        db.query(models.WishlistItem)
        .filter(
            models.WishlistItem.user_id == user_id,
            models.WishlistItem.product_id == payload.product_id,
        )
        .first()
    )

    if existing:
        db.delete(existing)
        db.commit()
        action = "removed"
    else:
        new_item = models.WishlistItem(
            user_id=user_id,
            product_id=payload.product_id,
        )
        db.add(new_item)
        db.commit()
        action = "added"

    wishlist = get_wishlist(db, user_id)
    wishlist.action = action
    return wishlist


# ═════════════════════════════════════════════════════════════════════════════
# ORDER CRUD
# ═════════════════════════════════════════════════════════════════════════════

def _simulate_supplier_forward(order: models.Order, items: List[models.OrderItem]) -> str:
    """
    Simulate forwarding the order to the dropshipping supplier.
    In production, this would call a supplier API or send a real email.
    Returns a mock tracking ID.
    """
    tracking_id = _generate_tracking_id()

    print("\n" + "═" * 60)
    print("📦  PAWVIBE SUPPLIER ORDER FORWARD — SIMULATED EMAIL")
    print("═" * 60)
    print(f"  To:        supplier@pawvibe-drops.in")
    print(f"  From:      orders@pawvibe.in")
    print(f"  Subject:   New Order #{order.id} — Please Fulfill")
    print(f"  Date:      {datetime.utcnow().strftime('%d %b %Y, %I:%M %p UTC')}")
    print("─" * 60)
    print(f"  Order ID:       #{order.id}")
    print(f"  Tracking ID:    {tracking_id}")
    print(f"  Total Amount:   ₹{order.total_amount:,.2f}")
    print(f"  Payment:        {order.payment_method.upper()}")
    print("\n  ORDER ITEMS:")
    for item in items:
        print(f"    • {item.product.name if item.product else f'Product #{item.product_id}'}")
        print(f"      Qty: {item.quantity}  |  Unit Price: ₹{item.unit_price}")
    if order.shipping_address:
        try:
            addr = json.loads(order.shipping_address)
            print("\n  SHIP TO:")
            print(f"    {addr.get('full_name', 'N/A')}")
            print(f"    {addr.get('address_line1', '')} {addr.get('address_line2', '')}")
            print(f"    {addr.get('city', '')}, {addr.get('state', '')} – {addr.get('pincode', '')}")
            print(f"    📞 {addr.get('phone', '')}")
        except json.JSONDecodeError:
            print(f"  Shipping Address: {order.shipping_address}")
    print("─" * 60)
    print("  ✅ Please dispatch within 2 business days.")
    print("     Update tracking at: https://supplier-portal.pawvibe-drops.in")
    print("═" * 60 + "\n")

    return tracking_id


def create_order(
    db: Session, user_id: int, payload: schemas.OrderCreate
) -> models.Order:
    """
    Place a new order.
    Flow:
      1. Validate all products exist and have stock
      2. Calculate total from live prices (not client-side)
      3. Create Order and OrderItem records
      4. Clear user's cart
      5. Simulate supplier forward email
      6. Award loyalty points to user
    """
    # ── Step 1: Validate products ─────────────────────────────────────────────
    order_items_data = []
    total_amount = 0.0

    for item_payload in payload.items:
        product = get_product_by_id(db, item_payload.product_id)
        if not product:
            raise ValueError(f"Product ID {item_payload.product_id} not found.")
        if product.stock < item_payload.quantity:
            raise ValueError(f"Insufficient stock for '{product.name}'.")

        line_total = product.price * item_payload.quantity
        total_amount += line_total
        order_items_data.append((product, item_payload.quantity))

    total_amount = round(total_amount, 2)

    # ── Step 2: Create Order record ───────────────────────────────────────────
    shipping_json = payload.shipping_address.model_dump_json()
    order = models.Order(
        user_id=user_id,
        total_amount=total_amount,
        status="processing",   # Immediately processing since it's dropshipping
        supplier_forwarded=False,
        shipping_address=shipping_json,
        payment_method=payload.payment_method,
    )
    db.add(order)
    db.flush()   # Get the order.id before committing

    # ── Step 3: Create OrderItem records ──────────────────────────────────────
    order_item_objects = []
    for product, quantity in order_items_data:
        order_item = models.OrderItem(
            order_id=order.id,
            product_id=product.id,
            quantity=quantity,
            unit_price=product.price,
        )
        db.add(order_item)
        order_item_objects.append(order_item)

    db.flush()

    # ── Step 4: Clear cart ────────────────────────────────────────────────────
    clear_cart(db, user_id)

    # ── Step 5: Simulate supplier forward ─────────────────────────────────────
    # Load products for the email print
    for oi in order_item_objects:
        oi.product = db.query(models.Product).get(oi.product_id)

    tracking_id = _simulate_supplier_forward(order, order_item_objects)
    order.supplier_forwarded = True
    order.tracking_id = tracking_id

    # ── Step 6: Award loyalty points ──────────────────────────────────────────
    user = get_user_by_id(db, user_id)
    if user:
        add_loyalty_points(db, user, total_amount)

    db.commit()
    db.refresh(order)
    return order


def get_orders_for_user(
    db: Session, user_id: int, skip: int = 0, limit: int = 20
) -> List[models.Order]:
    """Get all orders for a specific user, newest first."""
    return (
        db.query(models.Order)
        .options(joinedload(models.Order.order_items).joinedload(models.OrderItem.product))
        .filter(models.Order.user_id == user_id)
        .order_by(models.Order.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_order_by_id(db: Session, order_id: int) -> Optional[models.Order]:
    """Get a single order by ID with all items loaded."""
    return (
        db.query(models.Order)
        .options(joinedload(models.Order.order_items).joinedload(models.OrderItem.product))
        .filter(models.Order.id == order_id)
        .first()
    )


def get_all_orders(
    db: Session, skip: int = 0, limit: int = 50
) -> Tuple[List[models.Order], int]:
    """Admin: get all orders with count."""
    total = db.query(models.Order).count()
    orders = (
        db.query(models.Order)
        .options(joinedload(models.Order.order_items).joinedload(models.OrderItem.product))
        .order_by(models.Order.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return orders, total


def update_order_status(
    db: Session, order: models.Order, payload: schemas.OrderStatusUpdate
) -> models.Order:
    """Admin: update the status of an order."""
    order.status = payload.status
    db.commit()
    db.refresh(order)
    return order


def forward_order_to_supplier(
    db: Session, order: models.Order
) -> schemas.OrderForwardResponse:
    """
    Admin action: manually mark order as forwarded to supplier.
    Regenerates a tracking ID if needed.
    """
    items = (
        db.query(models.OrderItem)
        .options(joinedload(models.OrderItem.product))
        .filter(models.OrderItem.order_id == order.id)
        .all()
    )

    tracking_id = _simulate_supplier_forward(order, items)
    order.supplier_forwarded = True
    order.tracking_id = tracking_id
    if order.status == "pending":
        order.status = "processing"
    db.commit()

    return schemas.OrderForwardResponse(
        order_id=order.id,
        supplier_forwarded=True,
        tracking_id=tracking_id,
        message=f"Order #{order.id} successfully forwarded to supplier. Tracking: {tracking_id}",
    )


# ═════════════════════════════════════════════════════════════════════════════
# ADMIN STATS
# ═════════════════════════════════════════════════════════════════════════════

def get_dashboard_stats(db: Session) -> schemas.DashboardStats:
    """
    Aggregate statistics for the admin dashboard.
    All computed in a single pass over the DB.
    """
    total_orders    = db.query(models.Order).count()
    pending_orders  = db.query(models.Order).filter(models.Order.status == "pending").count()
    total_revenue   = db.query(func.sum(models.Order.total_amount)).scalar() or 0.0
    total_products  = db.query(models.Product).filter(models.Product.is_active == True).count()
    total_users     = db.query(models.User).filter(models.User.role == "customer").count()
    not_forwarded   = db.query(models.Order).filter(
        models.Order.supplier_forwarded == False
    ).count()

    return schemas.DashboardStats(
        total_orders=total_orders,
        pending_orders=pending_orders,
        total_revenue=round(total_revenue, 2),
        total_products=total_products,
        total_users=total_users,
        orders_not_forwarded=not_forwarded,
    )


def _build_order_response(order: models.Order) -> schemas.OrderResponse:
    """Convert an Order ORM object into an OrderResponse schema."""
    items = []
    for oi in order.order_items:
        items.append(
            schemas.OrderItemResponse(
                id=oi.id,
                product_id=oi.product_id,
                product_name=oi.product.name if oi.product else "Unknown Product",
                product_image=oi.product.image_url if oi.product else "",
                quantity=oi.quantity,
                unit_price=oi.unit_price,
                subtotal=round(oi.unit_price * oi.quantity, 2),
            )
        )
    return schemas.OrderResponse(
        id=order.id,
        user_id=order.user_id,
        total_amount=order.total_amount,
        status=order.status,
        supplier_forwarded=order.supplier_forwarded,
        shipping_address=order.shipping_address,
        payment_method=order.payment_method,
        tracking_id=order.tracking_id,
        items=items,
        created_at=order.created_at,
    )
