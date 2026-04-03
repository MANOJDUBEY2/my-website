"""
seed.py – Database Seeding Script for PawVibe
──────────────────────────────────────────────
Populates the database with:
  - 1 Admin user
  - 3 Sample customer users
  - 15 Trending 2026 dropshipping pet products with realistic Indian pricing

Run with:
  python -m app.seed

Products are selected based on 2026 trending dropshipping categories:
  - Summer pet comfort (cooling mats, fountains)
  - Enrichment & mental stimulation (snuffle mats, lick mats)
  - Grooming & hygiene (gloves, paw cleaners, dental toys)
  - Smart/automatic devices (feeders, water fountains)
  - Apparel & accessories (harnesses, bandanas)
"""

import os
import sys

# ── Add backend directory to path so we can import app modules ────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from app.database import SessionLocal, create_tables
from app import models
from app.auth import get_password_hash

load_dotenv()
console = Console()


# ─────────────────────────────────────────────────────────────────────────────
# Seed Data Definitions
# ─────────────────────────────────────────────────────────────────────────────

ADMIN_USER = {
    "name":     os.getenv("ADMIN_NAME", "PawVibe Admin"),
    "email":    os.getenv("ADMIN_EMAIL", "admin@pawvibe.in"),
    "password": os.getenv("ADMIN_PASSWORD", "PawVibe@2026!"),
    "role":     "admin",
}

SAMPLE_USERS = [
    {
        "name":     "Priya Sharma",
        "email":    "priya@example.com",
        "password": "Priya@1234",
        "role":     "customer",
    },
    {
        "name":     "Rohan Mehta",
        "email":    "rohan@example.com",
        "password": "Rohan@1234",
        "role":     "customer",
    },
    {
        "name":     "Ananya Verma",
        "email":    "ananya@example.com",
        "password": "Ananya@1234",
        "role":     "customer",
    },
]

# ── 15 Trending Dropshipping Products (2026 India) ────────────────────────────
# Pricing strategy:
#   - cost_price: what we pay the supplier (AliExpress/IndiaMART equivalent)
#   - price: selling price (2x–4x markup for healthy margins)
#   - margin target: 40–65%
PRODUCTS = [
    {
        "name":        "Premium Cooling Mat for Dogs & Cats",
        "slug":        "premium-cooling-mat-dogs-cats",
        "category":    "both",
        "price":       799.0,
        "cost_price":  280.0,
        "image_url":   "https://images.unsplash.com/photo-1587300003388-59208cc962cb?w=800&q=80",
        "description": (
            "Beat the Indian summer heat with this self-cooling gel mat! "
            "No electricity needed — just place it anywhere and watch your furry friend "
            "melt into it. Non-toxic, pressure-activated cooling technology. "
            "Perfect for dogs and cats of all sizes. Available in M, L, XL sizes. "
            "Foldable and portable — ideal for travel, crate, or couch use."
        ),
        "badges": "bestseller,trending,hot",
        "stock":  999,
        "rating": 4.8,
        "review_count": 1247,
    },
    {
        "name":        "Cat Water Fountain with Triple Filter",
        "slug":        "cat-water-fountain-triple-filter",
        "category":    "cat",
        "price":       1299.0,
        "cost_price":  420.0,
        "image_url":   "https://images.unsplash.com/photo-1548767797-d8c844163c4a?w=800&q=80",
        "description": (
            "Cats are naturally drawn to running water — this fountain satisfies that instinct "
            "while keeping them hydrated! Features a 3-stage filtration system (activated carbon + "
            "ion exchange resin + cotton filter) that removes chlorine, bad taste, and hair. "
            "Ultra-quiet pump (< 30dB). 2L capacity. LED light option. Perfect for multi-cat homes."
        ),
        "badges": "bestseller,trending",
        "stock":  999,
        "rating": 4.7,
        "review_count": 892,
    },
    {
        "name":        "Lick Mat for Dogs – Slow Feeder & Anxiety Relief",
        "slug":        "lick-mat-dogs-slow-feeder-anxiety-relief",
        "category":    "dog",
        "price":       499.0,
        "cost_price":  150.0,
        "image_url":   "https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=800&q=80",
        "description": (
            "The ultimate enrichment tool for anxious or bored dogs! Spread peanut butter, "
            "yogurt, or wet food across the textured surface to keep your pup engaged for "
            "20–30 minutes. Proven to reduce anxiety during grooming, storms, and fireworks. "
            "Made from food-grade silicone. Dishwasher safe. Freezer-friendly for extra long "
            "engagement. Vet-recommended for mental stimulation."
        ),
        "badges": "new,trending,hot",
        "stock":  999,
        "rating": 4.9,
        "review_count": 2103,
    },
    {
        "name":        "Pet Grooming Glove – Deshedding Brush",
        "slug":        "pet-grooming-glove-deshedding-brush",
        "category":    "both",
        "price":       399.0,
        "cost_price":  110.0,
        "image_url":   "https://images.unsplash.com/photo-1587300003388-59208cc962cb?w=800&q=80",
        "description": (
            "Turn grooming into bonding! This five-finger rubber massage glove captures loose "
            "hair, dander, and dirt with every stroke. Your pet will think it's just getting "
            "a relaxing massage — you'll be amazed at how much hair it collects. Works on dogs, "
            "cats, rabbits, and horses. Adjustable wrist strap fits all hand sizes. Machine "
            "washable. Reduces shedding by up to 90% with regular use."
        ),
        "badges": "bestseller",
        "stock":  999,
        "rating": 4.6,
        "review_count": 3456,
    },
    {
        "name":        "Muddy Paw Cleaner Cup – Portable Dog Paw Washer",
        "slug":        "muddy-paw-cleaner-cup-portable",
        "category":    "dog",
        "price":       599.0,
        "cost_price":  180.0,
        "image_url":   "https://images.unsplash.com/photo-1601758125946-6ec2ef64daf8?w=800&q=80",
        "description": (
            "No more muddy paw prints on your sofa or floors! This genius paw washer has "
            "soft silicone bristles inside that gently scrub dirt from between toes and paw pads. "
            "Just add water, insert paw, twist, and dry — takes 10 seconds per paw! "
            "Available in Small (up to Beagle), Medium (Labrador), and Large (German Shepherd). "
            "BPA-free, leak-proof lid included. A must-have for Indian monsoon season!"
        ),
        "badges": "trending,new",
        "stock":  999,
        "rating": 4.7,
        "review_count": 1678,
    },
    {
        "name":        "Snuffle Mat for Dogs – Nose Work Enrichment",
        "slug":        "snuffle-mat-dogs-nose-work-enrichment",
        "category":    "dog",
        "price":       699.0,
        "cost_price":  220.0,
        "image_url":   "https://images.unsplash.com/photo-1587300003388-59208cc962cb?w=800&q=80",
        "description": (
            "Dogs use their nose 10,000x more than humans — the Snuffle Mat lets them do "
            "what they love! Hide kibble or treats in the fabric strips and watch your dog "
            "engage in 20–30 minutes of natural foraging behaviour. Reduces meal-time speed, "
            "aids digestion, and provides mental exhaustion (a tired dog is a happy dog!). "
            "Handmade from fleece strips. Non-slip rubber base. Machine washable. "
            "Vet and trainer recommended for high-energy breeds."
        ),
        "badges": "bestseller,new",
        "stock":  999,
        "rating": 4.8,
        "review_count": 934,
    },
    {
        "name":        "Automatic Pet Feeder – 5L Wifi Smart Dispenser",
        "slug":        "automatic-pet-feeder-5l-wifi-smart",
        "category":    "both",
        "price":       3499.0,
        "cost_price":  1100.0,
        "image_url":   "https://images.unsplash.com/photo-1548767797-d8c844163c4a?w=800&q=80",
        "description": (
            "Feed your pet on schedule even when you're stuck in traffic or traveling! "
            "Control this smart feeder from your phone via the PetNet app. Set up to 8 "
            "meal schedules per day with custom portion sizes. Built-in voice recorder "
            "to call your pet to meals. Twist-lock lid prevents food theft. "
            "Compatible with Alexa and Google Home. 5L capacity feeds a medium dog for 2 weeks. "
            "Notifies you if the food bowl is empty. Works on WiFi 2.4GHz."
        ),
        "badges": "new,trending",
        "stock":  999,
        "rating": 4.5,
        "review_count": 567,
    },
    {
        "name":        "Adjustable No-Pull Dog Harness – Reflective",
        "slug":        "adjustable-no-pull-dog-harness-reflective",
        "category":    "dog",
        "price":       899.0,
        "cost_price":  290.0,
        "image_url":   "https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=800&q=80",
        "description": (
            "Walk with confidence and keep your dog safe! This padded no-pull harness "
            "distributes pressure across the chest (not throat), making walks comfortable "
            "even for reactive dogs. Dual attachment points (front + back) for training "
            "and walking. 360° reflective stitching keeps your dog visible at night. "
            "Easy step-in design with quick-release buckles. Breathable mesh padding. "
            "Available in XS–XL. Suitable for Indian breeds including Indie, Labrador, "
            "Husky, and Beagle."
        ),
        "badges": "bestseller,trending",
        "stock":  999,
        "rating": 4.7,
        "review_count": 2891,
    },
    {
        "name":        "Interactive Cat Teaser Wand – 10-Piece Set",
        "slug":        "interactive-cat-teaser-wand-10-piece-set",
        "category":    "cat",
        "price":       449.0,
        "cost_price":  130.0,
        "image_url":   "https://images.unsplash.com/photo-1514888286974-6c03e2ca1dba?w=800&q=80",
        "description": (
            "Keep your cat active, healthy, and mentally sharp with this 10-piece teaser set! "
            "Includes feathers, crinkle balls, bells, and plush attachments that rotate onto "
            "an extendable 90cm wand. Mimics natural prey movement to trigger your cat's "
            "hunting instinct. Studies show 15 minutes of wand play daily reduces aggression "
            "and obesity in indoor cats. Replaceable attachments. Telescoping wand collapses "
            "to 30cm for storage. Great gift for new cat parents!"
        ),
        "badges": "new,hot",
        "stock":  999,
        "rating": 4.6,
        "review_count": 1234,
    },
    {
        "name":        "Orthopedic Memory Foam Dog Bed – Large",
        "slug":        "orthopedic-memory-foam-dog-bed-large",
        "category":    "dog",
        "price":       2499.0,
        "cost_price":  780.0,
        "image_url":   "https://images.unsplash.com/photo-1601758125946-6ec2ef64daf8?w=800&q=80",
        "description": (
            "Give your senior dog or large breed the joint relief they deserve! "
            "This 4-inch memory foam base contours to your dog's body, reducing pressure "
            "on hips, elbows, and spine — especially beneficial for dogs with arthritis. "
            "Removable, machine-washable velvet cover. Water-resistant inner lining protects "
            "foam from accidents. Non-slip base keeps it in place on tiles (perfect for "
            "Indian homes!). Suitable for dogs up to 45kg. Vet-recommended for senior dogs "
            "and post-surgery recovery."
        ),
        "badges": "bestseller",
        "stock":  999,
        "rating": 4.8,
        "review_count": 756,
    },
    {
        "name":        "Dog Dental Chew Toy – Nylon Bacon Flavour",
        "slug":        "dog-dental-chew-toy-nylon-bacon",
        "category":    "dog",
        "price":       349.0,
        "cost_price":  100.0,
        "image_url":   "https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=800&q=80",
        "description": (
            "70% of dogs show signs of dental disease by age 2 — fight it deliciously! "
            "This nylon chew toy infused with real bacon flavour cleans teeth, massages "
            "gums, and satisfies the natural urge to chew without destroying your furniture. "
            "The bristled surface acts like a toothbrush with every bite. Suitable for "
            "aggressive chewers. Non-toxic, BPA-free nylon. Works for 6–12 months depending "
            "on chew intensity. Comes in Small (< 10kg), Medium, and Large sizes."
        ),
        "badges": "new",
        "stock":  999,
        "rating": 4.5,
        "review_count": 1889,
    },
    {
        "name":        "Self-Cleaning Cat Litter Box – Odour Control",
        "slug":        "self-cleaning-cat-litter-box-odour-control",
        "category":    "cat",
        "price":       3999.0,
        "cost_price":  1250.0,
        "image_url":   "https://images.unsplash.com/photo-1514888286974-6c03e2ca1dba?w=800&q=80",
        "description": (
            "Say goodbye to scooping forever! This enclosed self-cleaning litter box uses "
            "a rotating rake mechanism to sift waste into a sealed drawer after each use. "
            "Activated carbon filter neutralises 99% of odours — your guests will never know "
            "you have a cat! Safety sensor stops rotation if your cat re-enters. "
            "Compatible with all clumping litters. Large capacity holds 2 cats' waste for "
            "up to 7 days. Quiet motor (< 40dB). Includes 1-month supply of carbon filters."
        ),
        "badges": "new,trending,hot",
        "stock":  999,
        "rating": 4.7,
        "review_count": 423,
    },
    {
        "name":        "Pet Carrier Backpack – Airline Approved Bubble",
        "slug":        "pet-carrier-backpack-airline-approved-bubble",
        "category":    "both",
        "price":       1899.0,
        "cost_price":  580.0,
        "image_url":   "https://images.unsplash.com/photo-1548767797-d8c844163c4a?w=800&q=80",
        "description": (
            "Travel with your fur baby like a pro! This bubble backpack lets your cat or "
            "small dog see the world from a safe, cozy space-capsule window. "
            "Meets airline cabin size requirements (IndiGo, Air India, Vistara). "
            "Ventilated mesh sides ensure airflow. Padded shoulder straps and chest clip "
            "distribute weight for all-day comfort. Interior safety leash. "
            "Folds flat for storage. Loading hatch at top and front. "
            "Supports pets up to 8kg. Perfect for vet visits, markets, and flights."
        ),
        "badges": "trending,new",
        "stock":  999,
        "rating": 4.6,
        "review_count": 678,
    },
    {
        "name":        "Dog Calming Anxiety Vest – Thundershirt Style",
        "slug":        "dog-calming-anxiety-vest-thundershirt",
        "category":    "dog",
        "price":       1199.0,
        "cost_price":  370.0,
        "image_url":   "https://images.unsplash.com/photo-1587300003388-59208cc962cb?w=800&q=80",
        "description": (
            "Help your dog through Diwali fireworks, thunderstorms, car rides, and vet visits "
            "with this drug-free anxiety solution! The gentle, constant pressure mimics the "
            "calming effect of swaddling a baby — 80% of dogs show reduced anxiety within "
            "the first 20 minutes of wear. Lightweight breathable fabric keeps them cool "
            "in India's climate. Easy velcro wrap — no clips to fumble with. "
            "Machine washable. Works for separation anxiety, hyperactivity, and travel stress. "
            "Vet-endorsed. Available XS to XXL."
        ),
        "badges": "bestseller,hot",
        "stock":  999,
        "rating": 4.8,
        "review_count": 1102,
    },
    {
        "name":        "Stainless Steel Pet Food Bowl Set – Anti-Skid",
        "slug":        "stainless-steel-pet-food-bowl-set-anti-skid",
        "category":    "both",
        "price":       299.0,
        "cost_price":  85.0,
        "image_url":   "https://images.unsplash.com/photo-1548767797-d8c844163c4a?w=800&q=80",
        "description": (
            "Upgrade from plastic to premium! This set of 2 food-grade 304 stainless steel "
            "bowls are 100% rust-proof, scratch-resistant, and free from BPA and lead. "
            "The silicone non-slip base prevents bowl surfing across your floor during meals. "
            "Dishwasher safe. Wide base prevents whisker fatigue in cats. "
            "Available in 4 sizes from 250ml (cats/small dogs) to 2000ml (large breeds). "
            "Hygienic, durable, and stylish — a forever bowl your pet will never outgrow."
        ),
        "badges": "bestseller",
        "stock":  999,
        "rating": 4.5,
        "review_count": 4521,
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Seeding Functions
# ─────────────────────────────────────────────────────────────────────────────

def seed_users(db) -> None:
    """Seed admin and sample customer accounts."""
    console.print("\n[bold yellow]👤 Seeding Users...[/bold yellow]")

    all_users = [ADMIN_USER] + SAMPLE_USERS

    for user_data in all_users:
        # Check if user already exists
        existing = db.query(models.User).filter(
            models.User.email == user_data["email"]
        ).first()

        if existing:
            console.print(f"  [dim]⚡ Skipped (exists): {user_data['email']}[/dim]")
            continue

        user = models.User(
            name=user_data["name"],
            email=user_data["email"],
            hashed_password=get_password_hash(user_data["password"]),
            role=user_data["role"],
            loyalty_points=0 if user_data["role"] == "admin" else 50,  # Welcome bonus
        )
        db.add(user)
        console.print(
            f"  [green]✅ Created [{user_data['role']}]: {user_data['email']}[/green]"
        )

    db.commit()


def seed_products(db) -> None:
    """Seed the 15 trending dropshipping products."""
    console.print("\n[bold yellow]🛍️  Seeding Products...[/bold yellow]")

    table = Table(title="Products Added", show_header=True)
    table.add_column("ID",        style="cyan",    justify="right")
    table.add_column("Name",      style="white",   max_width=40)
    table.add_column("Category",  style="magenta")
    table.add_column("Price",     style="green",   justify="right")
    table.add_column("Cost",      style="red",     justify="right")
    table.add_column("Margin %",  style="yellow",  justify="right")
    table.add_column("Badges",    style="blue")

    for p_data in PRODUCTS:
        # Check if product with same slug already exists
        existing = db.query(models.Product).filter(
            models.Product.slug == p_data["slug"]
        ).first()

        if existing:
            console.print(f"  [dim]⚡ Skipped (exists): {p_data['name']}[/dim]")
            continue

        margin_pct = round(((p_data["price"] - p_data["cost_price"]) / p_data["price"]) * 100, 1)

        product = models.Product(
            name=         p_data["name"],
            slug=         p_data["slug"],
            category=     p_data["category"],
            price=        p_data["price"],
            cost_price=   p_data["cost_price"],
            image_url=    p_data["image_url"],
            description=  p_data["description"],
            badges=       p_data["badges"],
            stock=        p_data["stock"],
            rating=       p_data["rating"],
            review_count= p_data["review_count"],
        )
        db.add(product)
        db.flush()   # Get ID before committing

        table.add_row(
            str(product.id),
            p_data["name"][:38] + ("…" if len(p_data["name"]) > 38 else ""),
            p_data["category"],
            f"₹{p_data['price']:,.0f}",
            f"₹{p_data['cost_price']:,.0f}",
            f"{margin_pct}%",
            p_data["badges"],
        )

    db.commit()
    console.print(table)


def main() -> None:
    """Main seed runner."""
    console.print("\n[bold cyan]🐾 PawVibe Database Seeder[/bold cyan]")
    console.print("[dim]Creating tables if they don't exist...[/dim]")

    # Ensure tables are created
    create_tables()

    db = SessionLocal()
    try:
        seed_users(db)
        seed_products(db)
        console.print("\n[bold green]✨ Database seeding complete![/bold green]")
        console.print("\n[bold]Admin Login:[/bold]")
        console.print(f"  Email:    [cyan]{ADMIN_USER['email']}[/cyan]")
        console.print(f"  Password: [cyan]{ADMIN_USER['password']}[/cyan]")
        console.print(f"\n[bold]API Docs:[/bold] [link=http://localhost:8000/docs]http://localhost:8000/docs[/link]\n")
    except Exception as e:
        db.rollback()
        console.print(f"\n[bold red]❌ Seeding failed: {e}[/bold red]")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
