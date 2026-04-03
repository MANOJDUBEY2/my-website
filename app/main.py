"""
main.py – FastAPI Application Entry Point for PawVibe
──────────────────────────────────────────────────────
Responsibilities:
  - Create and configure the FastAPI app
  - Register all routers under /api/v1/
  - Configure CORS, global error handling, logging, rate limiting
  - Startup/shutdown event handlers
  - Health check endpoint

Architecture note:
  All business logic lives in crud.py.
  Routes only handle HTTP concerns (parse request, call crud, return response).
"""

import logging
import math
import os
import time
from contextlib import asynccontextmanager
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from .auth import (
    create_token_pair,
    get_current_user,
    require_admin,
    verify_refresh_token,
)
from . import crud, models, schemas
from .database import check_db_connection, create_tables, get_db

load_dotenv()

# ── Logging Configuration ─────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("pawvibe")

# ── Rate Limiter ──────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)

# ── CORS Origins ──────────────────────────────────────────────────────────────
CORS_ORIGINS_RAW = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5500,http://127.0.0.1:5500",
)
CORS_ORIGINS: List[str] = [origin.strip() for origin in CORS_ORIGINS_RAW.split(",")]


# ── Application Lifespan (startup + shutdown) ──────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs on startup and shutdown.
    - Startup: Create DB tables, log server ready message.
    - Shutdown: Log graceful shutdown.
    """
    # STARTUP ──────────────────────────────────────────────────────────────────
    logger.info("🐾 PawVibe API starting up...")
    create_tables()   # Idempotent: only creates if not exists
    db_ok = check_db_connection()
    if db_ok:
        logger.info("✅ Database connection: OK")
    else:
        logger.error("❌ Database connection: FAILED — check DATABASE_URL in .env")

    logger.info("🚀 PawVibe API is live at http://localhost:8000")
    logger.info("📚 Swagger UI: http://localhost:8000/docs")

    yield   # ← Application runs here

    # SHUTDOWN ─────────────────────────────────────────────────────────────────
    logger.info("🛑 PawVibe API shutting down gracefully...")


# ── FastAPI App Initialization ────────────────────────────────────────────────
app = FastAPI(
    title="PawVibe API",
    description=(
        "🐾 India's Most Loved Pet Happiness Store — Backend API\n\n"
        "Provides REST endpoints for products, cart, orders, wishlist, "
        "user authentication, and admin management.\n\n"
        "**Authentication:** Use the `/api/v1/auth/login` endpoint to get a Bearer token, "
        "then click 'Authorize' above and enter: `Bearer <your_token>`"
    ),
    version="2026.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── Rate Limiter Middleware ────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS Middleware ───────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)


# ── Request Logging Middleware ────────────────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every incoming request with method, path, and response time."""
    start_time = time.time()
    response = await call_next(request)
    duration = round((time.time() - start_time) * 1000, 2)   # ms
    logger.info(
        f"{request.method:6s} {request.url.path:50s} "
        f"→ {response.status_code} ({duration}ms)"
    )
    return response


# ── Global Exception Handler ──────────────────────────────────────────────────
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Return consistent JSON error format for all HTTPExceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error":   exc.detail,
            "message": str(exc.detail),
            "status_code": exc.status_code,
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Catch-all for unhandled exceptions — never expose stack traces in prod."""
    logger.exception(f"Unhandled exception on {request.method} {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error":   "INTERNAL_SERVER_ERROR",
            "message": "Something went wrong on our end. Please try again.",
            "status_code": 500,
        },
    )


# ═════════════════════════════════════════════════════════════════════════════
# HEALTH CHECK
# ═════════════════════════════════════════════════════════════════════════════

@app.get("/health", tags=["System"])
def health_check():
    """
    Quick health check endpoint.
    Returns 200 if the API and DB are running.
    Used by monitoring tools and Docker health checks.
    """
    db_ok = check_db_connection()
    return {
        "status":   "healthy" if db_ok else "degraded",
        "api":      "ok",
        "database": "ok" if db_ok else "error",
        "version":  "2026.1.0",
        "name":     "PawVibe API",
    }


# ═════════════════════════════════════════════════════════════════════════════
# AUTH ROUTES – /api/v1/auth/
# ═════════════════════════════════════════════════════════════════════════════

@app.post(
    "/api/v1/auth/register",
    response_model=schemas.APIResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Authentication"],
    summary="Register a new user account",
)
@limiter.limit("10/minute")
def register(
    request: Request,
    payload: schemas.UserRegister,
    db: Session = Depends(get_db),
):
    """
    Register a new customer account.
    - Validates email uniqueness
    - Hashes password with Bcrypt
    - Returns JWT token pair immediately (no separate login step needed)
    """
    # Check email uniqueness
    if crud.get_user_by_email(db, payload.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user = crud.create_user(db, payload)
    tokens = create_token_pair(user)
    logger.info(f"New user registered: {user.email}")

    return schemas.APIResponse(
        success=True,
        data={
            "user":   schemas.UserResponse.model_validate(user).model_dump(),
            "tokens": tokens,
        },
        message="Account created successfully! Welcome to PawVibe 🐾",
    )


@app.post(
    "/api/v1/auth/login",
    response_model=schemas.APIResponse,
    tags=["Authentication"],
    summary="Login and receive JWT tokens",
)
@limiter.limit("20/minute")
def login(
    request: Request,
    payload: schemas.UserLogin,
    db: Session = Depends(get_db),
):
    """
    Authenticate a user and return access + refresh tokens.
    Uses constant-time password comparison to prevent timing attacks.
    """
    user = crud.authenticate_user(db, payload.email, payload.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    tokens = create_token_pair(user)
    logger.info(f"User logged in: {user.email}")

    return schemas.APIResponse(
        success=True,
        data={
            "user":   schemas.UserResponse.model_validate(user).model_dump(),
            "tokens": tokens,
        },
        message=f"Welcome back, {user.name.split()[0]}! 🐾",
    )


@app.post(
    "/api/v1/auth/refresh",
    response_model=schemas.APIResponse,
    tags=["Authentication"],
    summary="Refresh access token using refresh token",
)
@limiter.limit("30/minute")
def refresh_token(
    request: Request,
    payload: schemas.TokenRefresh,
    db: Session = Depends(get_db),
):
    """
    Exchange a valid refresh token for a new access + refresh token pair.
    Old refresh token is effectively invalidated (client should discard it).
    """
    decoded = verify_refresh_token(payload.refresh_token)
    user_id = decoded.get("uid")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token payload.",
        )

    user = crud.get_user_by_id(db, user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or deactivated.",
        )

    tokens = create_token_pair(user)
    return schemas.APIResponse(
        success=True,
        data={"tokens": tokens},
        message="Tokens refreshed successfully.",
    )


@app.get(
    "/api/v1/auth/me",
    response_model=schemas.APIResponse,
    tags=["Authentication"],
    summary="Get current user profile",
)
def get_me(current_user: models.User = Depends(get_current_user)):
    """Return the currently authenticated user's profile."""
    return schemas.APIResponse(
        success=True,
        data=schemas.UserResponse.model_validate(current_user).model_dump(),
        message="User profile retrieved.",
    )


@app.put(
    "/api/v1/auth/me",
    response_model=schemas.APIResponse,
    tags=["Authentication"],
    summary="Update current user profile",
)
def update_me(
    payload: schemas.UserUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update the authenticated user's name and/or password."""
    updated_user = crud.update_user(db, current_user, payload)
    return schemas.APIResponse(
        success=True,
        data=schemas.UserResponse.model_validate(updated_user).model_dump(),
        message="Profile updated successfully.",
    )


# ═════════════════════════════════════════════════════════════════════════════
# PRODUCT ROUTES – /api/v1/products/
# ═════════════════════════════════════════════════════════════════════════════

@app.get(
    "/api/v1/products",
    response_model=schemas.APIResponse,
    tags=["Products"],
    summary="List all products with filtering and pagination",
)
def list_products(
    category:  Optional[str]   = Query(None, description="dog | cat | both"),
    min_price: Optional[float] = Query(None, ge=0),
    max_price: Optional[float] = Query(None, ge=0),
    badge:     Optional[str]   = Query(None, description="bestseller | new | trending | hot"),
    search:    Optional[str]   = Query(None, min_length=1, max_length=100),
    sort:      str             = Query("created_at_desc"),
    page:      int             = Query(1, ge=1),
    per_page:  int             = Query(12, ge=1, le=48),
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(lambda: None),
):
    """
    List products with optional filters.
    Returns paginated results. Public endpoint — no auth required.
    """
    products, total = crud.get_products(
        db,
        category=category,
        min_price=min_price,
        max_price=max_price,
        badge=badge,
        search=search,
        sort=sort,
        page=page,
        per_page=per_page,
    )

    pages = math.ceil(total / per_page) if per_page > 0 else 0
    product_list = [schemas.ProductPublic.model_validate(p).model_dump() for p in products]

    return schemas.APIResponse(
        success=True,
        data={
            "items":    product_list,
            "total":    total,
            "page":     page,
            "per_page": per_page,
            "pages":    pages,
        },
        message=f"{total} products found.",
    )


@app.get(
    "/api/v1/products/bestsellers",
    response_model=schemas.APIResponse,
    tags=["Products"],
    summary="Get bestselling products for homepage",
)
def get_bestsellers(limit: int = Query(6, ge=1, le=12), db: Session = Depends(get_db)):
    """Return top bestselling products. Used on the homepage."""
    products = crud.get_bestsellers(db, limit=limit)
    return schemas.APIResponse(
        success=True,
        data=[schemas.ProductPublic.model_validate(p).model_dump() for p in products],
        message="Bestsellers retrieved.",
    )


@app.get(
    "/api/v1/products/trending",
    response_model=schemas.APIResponse,
    tags=["Products"],
    summary="Get trending products for carousel",
)
def get_trending(limit: int = Query(8, ge=1, le=16), db: Session = Depends(get_db)):
    """Return trending products. Used in the hero carousel."""
    products = crud.get_trending_products(db, limit=limit)
    return schemas.APIResponse(
        success=True,
        data=[schemas.ProductPublic.model_validate(p).model_dump() for p in products],
        message="Trending products retrieved.",
    )


@app.get(
    "/api/v1/products/{product_id}",
    response_model=schemas.APIResponse,
    tags=["Products"],
    summary="Get a single product by ID",
)
def get_product(product_id: int, db: Session = Depends(get_db)):
    """Return a single product's full details. Used on the Product Detail Page."""
    product = crud.get_product_by_id(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")

    related = crud.get_related_products(db, product, limit=4)

    return schemas.APIResponse(
        success=True,
        data={
            "product": schemas.ProductPublic.model_validate(product).model_dump(),
            "related": [schemas.ProductPublic.model_validate(r).model_dump() for r in related],
        },
        message="Product retrieved.",
    )


@app.post(
    "/api/v1/products",
    response_model=schemas.APIResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Products"],
    summary="Create a new product (Admin only)",
)
def create_product(
    payload: schemas.ProductCreate,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin: Add a new product to the catalog."""
    product = crud.create_product(db, payload)
    logger.info(f"Admin {admin.email} created product: {product.name}")
    return schemas.APIResponse(
        success=True,
        data=schemas.ProductAdmin(
            **schemas.ProductPublic.model_validate(product).model_dump(),
            cost_price=product.cost_price,
            margin_inr=product.margin_inr,
            margin_percent=product.margin_percent,
        ).model_dump(),
        message=f"Product '{product.name}' created successfully.",
    )


@app.put(
    "/api/v1/products/{product_id}",
    response_model=schemas.APIResponse,
    tags=["Products"],
    summary="Update a product (Admin only)",
)
def update_product(
    product_id: int,
    payload: schemas.ProductUpdate,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin: Update an existing product's details."""
    product = crud.get_product_by_id(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")

    updated = crud.update_product(db, product, payload)
    logger.info(f"Admin {admin.email} updated product ID {product_id}")

    return schemas.APIResponse(
        success=True,
        data=schemas.ProductPublic.model_validate(updated).model_dump(),
        message=f"Product '{updated.name}' updated successfully.",
    )


@app.delete(
    "/api/v1/products/{product_id}",
    response_model=schemas.APIResponse,
    tags=["Products"],
    summary="Delete a product (Admin only)",
)
def delete_product(
    product_id: int,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin: Soft-delete a product (sets is_active=False)."""
    product = crud.get_product_by_id(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")

    crud.delete_product(db, product)
    logger.info(f"Admin {admin.email} deleted product ID {product_id}")

    return schemas.APIResponse(
        success=True,
        data=None,
        message=f"Product '{product.name}' deleted successfully.",
    )


# ═════════════════════════════════════════════════════════════════════════════
# CART ROUTES – /api/v1/cart/
# ═════════════════════════════════════════════════════════════════════════════

@app.get(
    "/api/v1/cart",
    response_model=schemas.APIResponse,
    tags=["Cart"],
    summary="Get current user's cart",
)
def get_cart(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the authenticated user's cart with all items and totals."""
    cart = crud.get_cart(db, current_user.id)
    return schemas.APIResponse(
        success=True,
        data=cart.model_dump(),
        message="Cart retrieved.",
    )


@app.post(
    "/api/v1/cart/add",
    response_model=schemas.APIResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Cart"],
    summary="Add an item to the cart",
)
def add_to_cart(
    payload: schemas.CartItemAdd,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add a product to the cart. If already in cart, increments quantity."""
    try:
        cart = crud.add_to_cart(db, current_user.id, payload)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return schemas.APIResponse(
        success=True,
        data=cart.model_dump(),
        message="Item added to cart! 🛒",
    )


@app.put(
    "/api/v1/cart/update/{item_id}",
    response_model=schemas.APIResponse,
    tags=["Cart"],
    summary="Update quantity of a cart item",
)
def update_cart_item(
    item_id: int,
    payload: schemas.CartItemUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update the quantity of a specific item in the user's cart."""
    try:
        cart = crud.update_cart_item(db, current_user.id, item_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return schemas.APIResponse(
        success=True,
        data=cart.model_dump(),
        message="Cart updated.",
    )


@app.delete(
    "/api/v1/cart/remove/{item_id}",
    response_model=schemas.APIResponse,
    tags=["Cart"],
    summary="Remove an item from the cart",
)
def remove_from_cart(
    item_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove a specific item from the user's cart."""
    cart = crud.remove_from_cart(db, current_user.id, item_id)
    return schemas.APIResponse(
        success=True,
        data=cart.model_dump(),
        message="Item removed from cart.",
    )


# ═════════════════════════════════════════════════════════════════════════════
# WISHLIST ROUTES – /api/v1/wishlist/
# ═════════════════════════════════════════════════════════════════════════════

@app.get(
    "/api/v1/wishlist",
    response_model=schemas.APIResponse,
    tags=["Wishlist"],
    summary="Get current user's wishlist",
)
def get_wishlist(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the authenticated user's wishlist with all product details."""
    wishlist = crud.get_wishlist(db, current_user.id)
    return schemas.APIResponse(
        success=True,
        data=wishlist.model_dump(),
        message="Wishlist retrieved.",
    )


@app.post(
    "/api/v1/wishlist/toggle",
    response_model=schemas.APIResponse,
    tags=["Wishlist"],
    summary="Toggle a product in/out of wishlist",
)
def toggle_wishlist(
    payload: schemas.WishlistToggle,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Toggle wishlist membership.
    If the product is in the wishlist → remove it.
    If not → add it.
    """
    try:
        wishlist = crud.toggle_wishlist(db, current_user.id, payload)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    action_msg = "added to" if wishlist.action == "added" else "removed from"
    return schemas.APIResponse(
        success=True,
        data=wishlist.model_dump(),
        message=f"Product {action_msg} wishlist ❤️",
    )


# ═════════════════════════════════════════════════════════════════════════════
# ORDER ROUTES – /api/v1/orders/
# ═════════════════════════════════════════════════════════════════════════════

@app.post(
    "/api/v1/orders",
    response_model=schemas.APIResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Orders"],
    summary="Place a new order",
)
def create_order(
    payload: schemas.OrderCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Place an order.
    - Validates all products and quantities
    - Calculates totals from live prices (not client prices)
    - Clears the user's cart
    - Simulates supplier email forwarding
    - Awards loyalty points
    """
    try:
        order = crud.create_order(db, current_user.id, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    order_data = crud._build_order_response(order)
    logger.info(
        f"Order #{order.id} placed by {current_user.email} "
        f"— ₹{order.total_amount:,.2f} — Tracking: {order.tracking_id}"
    )

    return schemas.APIResponse(
        success=True,
        data=order_data.model_dump(),
        message=(
            f"🎉 Order #{order.id} placed successfully! "
            f"Tracking ID: {order.tracking_id}. "
            f"Expected delivery in 3–7 business days."
        ),
    )


@app.get(
    "/api/v1/orders",
    response_model=schemas.APIResponse,
    tags=["Orders"],
    summary="Get order history for current user",
)
def get_my_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the authenticated user's order history, newest first."""
    orders = crud.get_orders_for_user(db, current_user.id, skip=skip, limit=limit)
    order_data = [crud._build_order_response(o).model_dump() for o in orders]

    return schemas.APIResponse(
        success=True,
        data=order_data,
        message=f"{len(order_data)} orders found.",
    )


@app.get(
    "/api/v1/orders/{order_id}",
    response_model=schemas.APIResponse,
    tags=["Orders"],
    summary="Get a specific order (own orders or admin)",
)
def get_order(
    order_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get a specific order by ID.
    - Regular users can only access their own orders.
    - Admins can access any order.
    """
    order = crud.get_order_by_id(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")

    # Non-admins can only see their own orders
    if current_user.role != "admin" and order.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this order.",
        )

    return schemas.APIResponse(
        success=True,
        data=crud._build_order_response(order).model_dump(),
        message="Order retrieved.",
    )


# ═════════════════════════════════════════════════════════════════════════════
# ADMIN ROUTES – /api/v1/admin/
# ═════════════════════════════════════════════════════════════════════════════

@app.get(
    "/api/v1/admin/stats",
    response_model=schemas.APIResponse,
    tags=["Admin"],
    summary="Get dashboard statistics",
)
def admin_stats(
    admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Return aggregate statistics for the admin dashboard."""
    stats = crud.get_dashboard_stats(db)
    return schemas.APIResponse(
        success=True,
        data=stats.model_dump(),
        message="Dashboard stats retrieved.",
    )


@app.get(
    "/api/v1/admin/orders",
    response_model=schemas.APIResponse,
    tags=["Admin"],
    summary="Get all orders (Admin only)",
)
def admin_get_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin: Return all orders from all users with pagination."""
    orders, total = crud.get_all_orders(db, skip=skip, limit=limit)
    order_data = [crud._build_order_response(o).model_dump() for o in orders]

    return schemas.APIResponse(
        success=True,
        data={
            "items": order_data,
            "total": total,
        },
        message=f"{total} total orders.",
    )


@app.put(
    "/api/v1/admin/orders/{order_id}/status",
    response_model=schemas.APIResponse,
    tags=["Admin"],
    summary="Update order status (Admin only)",
)
def admin_update_order_status(
    order_id: int,
    payload: schemas.OrderStatusUpdate,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin: Update the status of any order."""
    order = crud.get_order_by_id(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")

    updated = crud.update_order_status(db, order, payload)
    logger.info(f"Admin {admin.email} updated order #{order_id} status → {payload.status}")

    return schemas.APIResponse(
        success=True,
        data=crud._build_order_response(updated).model_dump(),
        message=f"Order #{order_id} status updated to '{payload.status}'.",
    )


@app.post(
    "/api/v1/admin/orders/{order_id}/forward",
    response_model=schemas.APIResponse,
    tags=["Admin"],
    summary="Forward order to supplier (Admin only)",
)
def admin_forward_order(
    order_id: int,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Admin: Mark an order as forwarded to the dropshipping supplier.
    Simulates sending a supplier email and generates a tracking ID.
    """
    order = crud.get_order_by_id(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")

    result = crud.forward_order_to_supplier(db, order)
    logger.info(
        f"Admin {admin.email} forwarded order #{order_id} "
        f"to supplier. Tracking: {result.tracking_id}"
    )

    return schemas.APIResponse(
        success=True,
        data=result.model_dump(),
        message=result.message,
    )


@app.get(
    "/api/v1/admin/users",
    response_model=schemas.APIResponse,
    tags=["Admin"],
    summary="Get all users (Admin only)",
)
def admin_get_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin: Return all registered users."""
    users = crud.get_all_users(db, skip=skip, limit=limit)
    return schemas.APIResponse(
        success=True,
        data=[schemas.UserResponse.model_validate(u).model_dump() for u in users],
        message=f"{len(users)} users found.",
    )


# ═════════════════════════════════════════════════════════════════════════════
# RUN SERVER (for run.py)
# ═════════════════════════════════════════════════════════════════════════════

# backend/run.py
# (This is a separate file but documented here for completeness)
"""
# backend/run.py
import uvicorn
from app.main import app

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
        access_log=True,
    )
"""
