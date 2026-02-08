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

@app.context_processor
def inject_user():
    is_admin = session.get('role') == 'admin'
    return {"is_admin": is_admin}

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

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        phone = request.form.get("phone", "")
        message = request.form["message"]

        flash("Благодарим ви за съобщението! Ще се свържем с вас скоро.")
        return redirect(url_for("contact"))

    return render_template("contact.html")

@app.route("/online_order", methods=["GET", "POST"])
@login_required
def online_order():
    if request.method == "POST":
        delivery_date = request.form["delivery_date"]
        delivery_time = request.form["delivery_time"]
        delivery_address = request.form["delivery_address"]
        customer_name = request.form["customer_name"]
        customer_phone = request.form["customer_phone"]
        notes = request.form.get("notes", "")

        flash(f"Вашата поръчка е приета! Доставка на {delivery_date} в {delivery_time} часа.")
        return redirect(url_for("index"))

    return render_template("online_order.html")

@app.route("/admin/products/add", methods=["GET", "POST"], endpoint='admin_add_product')
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

@app.route("/admin/panel", endpoint='admin_panel')
@admin_required
def admin_panel():
    return render_template("admin_panel.html")

@app.route("/admin/products", endpoint='admin_products')
@admin_required
def admin_products():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM products")
    products = cursor.fetchall()
    return render_template("admin_products.html", products=products)

@app.route("/admin/statistics", endpoint='admin_statistics')
@admin_required
def admin_statistics():
    # Placeholder logic for statistics, you would replace this with actual logic
    return render_template("admin_statistics.html")


@app.route("/admin/users", endpoint='admin_users')
@admin_required

def admin_users():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT id, realname, username, role FROM users")
    users = cursor.fetchall()
    return render_template("admin_users.html", users=users)

@app.route("/admin/users/update/<int:user_id>", methods=["POST"], endpoint='admin_update_user')
@admin_required
def admin_update_user(user_id):
    realname = request.form["realname"]
    role = request.form["role"]

    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute(
            "UPDATE users SET realname=%s, role=%s WHERE id=%s",
            (realname, role, user_id)
        )
        db.commit()
        flash("User updated successfully.")
    except mysql.connector.Error as err:
        db.rollback()
        flash(f"Error updating user: {err}")
    return redirect(url_for("admin_users"))

@app.route("/admin/users/<int:user_id>", endpoint='user_profile')
@admin_required
def user_profile(user_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT id, realname, username, role FROM users WHERE id=%s", (user_id,))
    user = cursor.fetchone()
    if not user:
        flash("User not found.")
        return redirect(url_for('index'))
    cursor.execute("SELECT id, address_line1, address_line2, city, state, postal_code, country, is_default FROM delivery WHERE user_id=%s ORDER BY is_default DESC, id ASC", (user_id,))
    addresses = cursor.fetchall()
    can_edit_role = True  # admin always can edit
    return render_template("user_profile.html", user=user, can_edit_role=can_edit_role, addresses=addresses)

@app.route("/admin/users/<int:user_id>", methods=["POST"], endpoint='update_profile')
@admin_required
def update_profile(user_id):
    realname = request.form.get('realname')
    role = request.form.get('role')
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("UPDATE users SET realname=%s, role=%s WHERE id=%s", (realname, role, user_id))
        db.commit()
        flash("Profile updated.")
    except mysql.connector.Error as err:
        db.rollback()
        flash(f"Error: {err}")
    return redirect(url_for('user_profile', user_id=user_id))

@app.route("/admin/users/<int:user_id>/add_address", methods=["GET", "POST"], endpoint='add_address')
@admin_required
def add_address(user_id):
    if request.method == "POST":
        address_line1 = request.form["address_line1"]
        address_line2 = request.form.get("address_line2") or None
        city = request.form["city"]
        state = request.form.get("state") or None
        postal_code = request.form.get("postal_code") or None
        country = request.form["country"]
        is_default = 1 if 'is_default' in request.form else 0

        db = get_db()
        cursor = db.cursor()
        try:
            cursor.execute(
                "INSERT INTO delivery (user_id, address_line1, address_line2, city, state, postal_code, country, is_default) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (user_id, address_line1, address_line2, city, state, postal_code, country, is_default)
            )
            if is_default:
                cursor.callproc('SetDefaultDeliveryAddress', (user_id, cursor.lastrowid))
            db.commit()
            flash("Address added.")
        except mysql.connector.Error as err:
            db.rollback()
            flash(f"Error: {err}")
        return redirect(url_for("user_profile", user_id=user_id))

    return render_template("add_address.html", user_id=user_id)

@app.route("/admin/users/<int:user_id>/edit_address/<int:address_id>", methods=["GET", "POST"], endpoint='edit_address')
@admin_required
def edit_address(user_id, address_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    if request.method == "POST":
        address_line1 = request.form["address_line1"]
        address_line2 = request.form.get("address_line2") or None
        city = request.form["city"]
        state = request.form.get("state") or None
        postal_code = request.form.get("postal_code") or None
        country = request.form["country"]
        is_default = 1 if 'is_default' in request.form else 0

        try:
            cursor.execute(
                "UPDATE delivery SET address_line1=%s, address_line2=%s, city=%s, state=%s, postal_code=%s, country=%s, is_default=%s WHERE id=%s AND user_id=%s",
                (address_line1, address_line2, city, state, postal_code, country, is_default, address_id, user_id)
            )
            if is_default:
                cursor.callproc('SetDefaultDeliveryAddress', (user_id, address_id))
            db.commit()
            flash("Address updated.")
        except mysql.connector.Error as err:
            db.rollback()
            flash(f"Error: {err}")
        return redirect(url_for("user_profile", user_id=user_id))

    cursor.execute("SELECT * FROM delivery WHERE id=%s AND user_id=%s", (address_id, user_id))
    address = cursor.fetchone()
    if not address:
        flash("Address not found.")
        return redirect(url_for("user_profile", user_id=user_id))

    return render_template("edit_address.html", user_id=user_id, address=address)

@app.route("/admin/users/<int:user_id>/set_default/<int:address_id>", endpoint='set_default_address')
@admin_required
def set_default_address(user_id, address_id):
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.callproc('SetDefaultDeliveryAddress', (user_id, address_id))
        db.commit()
        flash("Default address changed.")
    except mysql.connector.Error as err:
        db.rollback()
        flash(f"Error: {err}")
    return redirect(url_for("user_profile", user_id=user_id))

@app.route("/admin/products/delete/<int:product_id>", endpoint='admin_delete_product')
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
