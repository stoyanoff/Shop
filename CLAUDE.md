# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Flask-based flower shop web application (university diploma project — ФлораСтил). Bulgarian-language storefront with product catalogue, cart, checkout, user auth, admin panel, and custom bouquet orders. Backend is MariaDB/MySQL; no ORM — all queries are raw SQL.

## Running the App

```bash
# Install dependencies (uses uv)
uv sync

# Run development server
uv run flask run
```

Requires Python 3.13 (see `.python-version`). The database runs on a separate MariaDB server (`ssh dbmy`, 192.168.1.112); connection details live in `config.py` (gitignored).

## config.py (gitignored — must be created locally)

```python
DB_CONFIG = {
    "host": "192.168.1.112",
    "user": "shop",
    "password": "1234",
    "database": "shop"
}
SECRET_KEY = "dev"
```

## Database Setup

```bash
mysql -u shop -p shop < mysql.sql
```

`mysql.sql` includes all tables, seed data, the `payments` table, and the `SetDefaultDeliveryAddress` stored procedure.

**Admin login:** `admin` / `1234`

## Architecture

Everything lives in one file: **`app.py`** (~950 lines). There are no blueprints or separate modules.

### Database Access Pattern
Per-request DB connection via Flask's `g` object:
```python
def get_db():              # opens mysql.connector connection on first call
@app.teardown_appcontext   # closes it at end of request
```

### Auth
- Session-based (`flask.session`) storing `user_id`, `username`, `role`
- `@login_required` and `@admin_required` decorators gate access
- Roles: `customer` (default) or `admin`

### Template Context
`inject_global_data()` context processor injects `categories`, `services`, and `is_admin` into all templates on every request — used by the navbar.

### Product Filtering (index route)
`GET /` accepts:
- `?category=<slug>` — filter by category
- `?service=<slug>` — filter by service
- `?service=custombouquet` — renders custom bouquet order form instead of product list

### User Profile
`/my-profile` — logged-in users see their order history (orders + items + totals). Uses `orders` and `order_items` tables.

### Image Handling
1. **Uploaded file** — processed with Pillow (max 1024×768, quality 85), saved to `static/images/products/<uuid>.<ext>`
2. **External URL** — stored as-is in the `image` column

### Admin Panel
All routes under `/admin/` require `@admin_required`. CRUD for: products, categories, services, users, orders. Delivery addresses use stored procedure `SetDefaultDeliveryAddress(user_id, address_id)`.

## Database Schema

| Table | Purpose |
|---|---|
| `users` | id, username, password_hash, role, realname |
| `categories` | id, name, slug |
| `services` | id, name, slug |
| `products` | id, name, description, price, stock, image, category_id, service_id |
| `orders` | id, user_id, created_at, status |
| `order_items` | id, order_id, product_id, quantity, price |
| `delivery` | id, user_id, address fields, is_default |
| `payments` | id, order_id, amount, method, status, created_at |
| `custom_bouquet_orders` | id, user_id, flower_types, flower_count, bouquet_color, has_card, card_text, status |

**Stored procedure:** `SetDefaultDeliveryAddress(user_id, address_id)` — clears all default addresses for user then sets the specified one.

## Cart

`session["cart"]` — `{product_id: quantity}` dict. Checkout creates `orders` + `order_items` rows then clears it.

## Docs/

- `FlораСтил_Презентация.pptx` — 16-slide defense presentation (includes real screenshots)
- `Answers.docx` — 5 potential defense questions, full + short answers
- `Отговори_на_въпроси.md` — same in markdown
- `screenshots/` — Playwright screenshots of all key pages

## Linting

```bash
uv run ruff check app.py
uv run ruff format app.py
```
