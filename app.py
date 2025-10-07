from flask import Flask, render_template, request, redirect, url_for, session, flash, g
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from config import DB_CONFIG, SECRET_KEY
import functools

app = Flask(__name__)
app.secret_key = SECRET_KEY

def get_db():
    if 'db' not in g:
        g.db = mysql.connector.connect(**DB_CONFIG)
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return view(**kwargs)
    return wrapped_view

def admin_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if not session.get('role') == 'admin':
            flash("You are not authorized to access this page.")
            return redirect(url_for('index'))
        return view(**kwargs)
    return wrapped_view

@app.route("/")
def index():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM products")
    products = cursor.fetchall()
    return render_template("index.html", products=products)

@app.route("/product/<int:product_id>")
def product_detail(product_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM products WHERE id=%s", (product_id,))
    product = cursor.fetchone()
    return render_template("product.html", product=product)

@app.route("/add_to_cart/<int:product_id>")
def add_to_cart(product_id):
    cart = session.get("cart", {})
    cart[str(product_id)] = cart.get(str(product_id), 0) + 1
    session["cart"] = cart
    return redirect(url_for("cart"))

@app.route("/cart")
def cart():
    cart = session.get("cart", {})
    items = []
    total = 0
    if cart:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        for pid, qty in cart.items():
            cursor.execute("SELECT * FROM products WHERE id=%s", (pid,))
            product = cursor.fetchone()
            if product:
                subtotal = product["price"] * qty
                total += subtotal
                items.append({
                    "id": product["id"],
                    "name": product["name"],
                    "price": product["price"],
                    "quantity": qty,
                    "subtotal": subtotal
                })
    return render_template("cart.html", items=items, total=total)

@app.route("/checkout")
@login_required
def checkout():
    cart = session.get("cart", {})
    if not cart:
        return redirect(url_for("index"))

    db = get_db()
    cursor = db.cursor()
    user_id = session.get("user_id")
    try:
        cursor.execute("INSERT INTO orders (user_id) VALUES (%s)", (user_id,))
        order_id = cursor.lastrowid

        for pid, qty in cart.items():
            cursor.execute("SELECT price FROM products WHERE id=%s", (pid,))
            price = cursor.fetchone()[0]
            cursor.execute(
                "INSERT INTO order_items (order_id, product_id, quantity, price) VALUES (%s, %s, %s, %s)",
                (order_id, pid, qty, price)
            )
        db.commit()
        session.pop("cart", None)
        flash("Order placed successfully!")
    except mysql.connector.Error as err:
        db.rollback()
        flash(f"An error occurred: {err}")
        return redirect(url_for('cart'))

    return render_template("checkout.html", order_id=order_id)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        password_hash = generate_password_hash(password)

        db = get_db()
        cursor = db.cursor()
        try:
            cursor.execute(
                "INSERT INTO users (username, password_hash) VALUES (%s, %s)",
                (username, password_hash)
            )
            db.commit()
            flash("Registration successful! Please log in.")
            return redirect(url_for("login"))
        except mysql.connector.Error:
            flash("Username already exists.")
            return redirect(url_for("register"))

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
        user = cursor.fetchone()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user.get("role")
            flash(f"Welcome, {user['username']}!")
            return redirect(url_for("index"))
        else:
            flash("Invalid username or password.")
            return redirect(url_for("login"))

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.")
    return redirect(url_for("index"))

@app.route("/admin/products")
@admin_required
def admin_products():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM products")
    products = cursor.fetchall()
    return render_template("admin_products.html", products=products)

@app.route("/admin/products/add", methods=["GET", "POST"])
@admin_required
def admin_add_product():
    if request.method == "POST":
        name = request.form["name"]
        desc = request.form["description"]
        price = request.form["price"]
        stock = request.form["stock"]

        db = get_db()
        cursor = db.cursor()
        try:
            cursor.execute(
                "INSERT INTO products (name, description, price, stock) VALUES (%s, %s, %s, %s)",
                (name, desc, price, stock)
            )
            db.commit()
            flash("Product added successfully.")
        except mysql.connector.Error as err:
            db.rollback()
            flash(f"Error adding product: {err}")
        return redirect(url_for("admin_products"))

    return render_template("admin_add_product.html")

@app.route("/admin/products/delete/<int:product_id>")
@admin_required
def admin_delete_product(product_id):
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("DELETE FROM products WHERE id=%s", (product_id,))
        db.commit()
        flash("Product deleted.")
    except mysql.connector.Error as err:
        db.rollback()
        flash(f"Error deleting product: {err}")
    return redirect(url_for("admin_products"))

@app.route("/admin/orders")
@admin_required
def admin_orders():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("""
        SELECT o.id, o.created_at, o.status, u.username
        FROM orders o
        LEFT JOIN users u ON o.user_id = u.id
        ORDER BY o.created_at DESC
    """)
    orders = cursor.fetchall()
    return render_template("admin_orders.html", orders=orders)

@app.route("/admin/orders/<int:order_id>")
@admin_required
def admin_order_detail(order_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("""
        SELECT oi.quantity, oi.price, p.name
        FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        WHERE oi.order_id=%s
    """, (order_id,))
    items = cursor.fetchall()
    return render_template("admin_order_detail.html", items=items, order_id=order_id)