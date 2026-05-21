# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Flask-based flower shop web application (university diploma project). Bulgarian-language storefront with product catalogue, cart, checkout, user auth, and an admin panel. Backend is MariaDB/MySQL; no ORM — all queries are raw SQL.

## Running the App

```bash
# Install dependencies (uses uv)
uv sync

# Run development server
uv run flask run

# Or directly
uv run python app.py
```

Requires Python 3.13 (see `.python-version`). The database runs on a separate MariaDB server; connection details live in `config.py` (gitignored — create it locally, see structure below).

## config.py (gitignored — must be created locally)

```python
DB_CONFIG = {
    "host": "192.168.1.112",
    "user": "shop",
    "password": "...",
    "database": "shop"
}
SECRET_KEY = "dev"
```

## Database Setup

Import the full schema and seed data:
```bash
mysql -u shop -p shop < mysql.sql
```

The `custom_bouquet_table.sql` contains the `custom_bouquet_orders` table definition (also included in `mysql.sql`).

**Important:** The stored procedure `SetDefaultDeliveryAddress(user_id, address_id)` is called in `app.py` but is **not** included in `mysql.sql`. It must be created manually before delivery address management will work.

## Architecture

Everything lives in one file: **`app.py`** (~900 lines). There are no blueprints or separate modules.

### Database Access Pattern
A new DB connection is created per request via Flask's `g` object:
```python
def get_db():           # opens mysql.connector connection on first call
@app.teardown_appcontext  # closes it at end of request
```

### Auth
- Session-based (`flask.session`) storing `user_id`, `username`, `role`
- Two decorators gate access: `@login_required` and `@admin_required`
- Roles: `customer` (default) or `admin`

### Template Context
`inject_global_data()` context processor runs on every request and injects `categories`, `services`, and `is_admin` into all templates — used by the navbar.

### Product Filtering (index route)
The `GET /` route accepts query params:
- `?category=<slug>` — filter by category slug
- `?service=<slug>` — filter by service slug
- `?service=custombouquet` — special: renders the custom bouquet order form instead of product list

### Image Handling
Product images can be:
1. **Uploaded file** — processed with Pillow (resized to 1024×768 max, quality 85), saved to `static/images/products/<uuid>.<ext>`
2. **External URL** — stored as-is in the `image` column

### Admin Panel
All admin routes are under `/admin/` and require `@admin_required`. CRUD operations for: products, categories, services, users, orders. User profile view also handles delivery addresses (add/edit/set default).

## Database Schema (key tables)

| Table | Purpose |
|---|---|
| `users` | id, username, password_hash, role, realname |
| `categories` | id, name, slug |
| `services` | id, name, slug |
| `products` | id, name, description, price, stock, image, category_id, service_id |
| `orders` | id, user_id, created_at, status |
| `order_items` | id, order_id, product_id, quantity, price |
| `delivery` | id, user_id, address fields, is_default |
| `custom_bouquet_orders` | id, user_id, flower_types, flower_count, bouquet_color, has_card, card_text, status |

## Cart

Stored entirely in the Flask session as `session["cart"]` — a `{product_id: quantity}` dict. Checkout creates an `orders` row and `order_items` rows, then clears the cart.

## Linting

Ruff is configured (`.ruff_cache/` present):
```bash
uv run ruff check app.py
uv run ruff format app.py
```
