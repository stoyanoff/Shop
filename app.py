from flask import Flask, render_template, request, redirect, url_for, session, flash, g
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from config import DB_CONFIG, SECRET_KEY
import functools
import os
from PIL import Image
import uuid

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
def inject_global_data():
    is_admin = session.get('role') == 'admin'
    categories = []
    services = []
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT * FROM categories")
        categories = cursor.fetchall()
        cursor.execute("SELECT * FROM services")
        services = cursor.fetchall()
    except Exception:
        pass
    return {"is_admin": is_admin, "categories": categories, "services": services}

@app.route("/", methods=["GET", "POST"])
def index():
    category_slug = request.args.get('category')
    service_slug = request.args.get('service')

    # Handle custom bouquet service
    if service_slug == 'custombouquet':
        if request.method == "POST":
            if 'user_id' not in session:
                flash("Вие трябва да сте регистриран и логнат потребител, за да имате достъп до тази услуга!")
                return redirect(url_for('login'))

            # Process custom bouquet form
            flower_types = request.form.get('flower_types', '')
            try:
                flower_count = int(request.form.get('flower_count', 0))
            except (ValueError, TypeError):
                flower_count = 0
            bouquet_color = request.form.get('bouquet_color', '')
            has_card = 'has_card' in request.form
            card_text = request.form.get('card_text', '') if has_card else None

            # Validation
            if not flower_types or len(flower_types) > 254:
                flash("Моля въведете валидни видове цветя (до 254 символа).")
                return render_template("custom_bouquet.html")

            if flower_count <= 0 or flower_count > 99:
                flash("Броят цветя трябва да е между 1 и 99.")
                return render_template("custom_bouquet.html")

            if not bouquet_color or len(bouquet_color) > 254:
                flash("Моля въведете валиден цвят на букета (до 254 символа).")
                return render_template("custom_bouquet.html")

            if has_card and card_text and len(card_text) > 1024:
                flash("Текстът на картичката не трябва да надвишава 1024 символа.")
                return render_template("custom_bouquet.html")

            # Save to database
            db = get_db()
            cursor = db.cursor()
            try:
                cursor.execute("""
                    INSERT INTO custom_bouquet_orders
                    (user_id, flower_types, flower_count, bouquet_color, has_card, card_text)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (session['user_id'], flower_types, flower_count, bouquet_color, has_card, card_text))
                db.commit()
                flash("Вашата поръчка за букет по желание е получена! Ще се свържем с Вас скоро.")
                return redirect(url_for('index'))
            except mysql.connector.Error as err:
                db.rollback()
                flash(f"Възникна грешка при запазването: {err}")
                return render_template("custom_bouquet.html")

        # Show custom bouquet form for GET request
        return render_template("custom_bouquet.html")

    db = get_db()
    cursor = db.cursor(dictionary=True)

    if category_slug:
        cursor.execute("""
            SELECT p.* FROM products p
            JOIN categories c ON p.category_id = c.id
            WHERE c.slug = %s
        """, (category_slug,))
    elif service_slug:
        cursor.execute("""
            SELECT p.* FROM products p
            JOIN services s ON p.service_id = s.id
            WHERE s.slug = %s
        """, (service_slug,))
    else:
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
def online_order():
    if request.method == "POST":
        if 'user_id' not in session:
            flash("Вие трябва да сте регистриран и логнат потребител, за да имате достъп до тази услуга!")
            return redirect(url_for('login'))

        delivery_date = request.form["delivery_date"]
        delivery_time = request.form["delivery_time"]
        delivery_address = request.form["delivery_address"]
        customer_name = request.form["customer_name"]
        customer_phone = request.form["customer_phone"]
        notes = request.form.get("notes", "")

        flash(f"Вашата поръчка е приета! Доставка на {delivery_date} в {delivery_time} часа.")
        return redirect(url_for("index"))

    return render_template("online_order.html")

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def process_image(image_file, max_size=(1024, 768)):
    """Process and resize image if needed"""
    try:
        img = Image.open(image_file)

        # Convert to RGB if necessary (for PNG with transparency)
        if img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGB')

        # Resize if larger than max_size
        if img.size[0] > max_size[0] or img.size[1] > max_size[1]:
            img.thumbnail(max_size, Image.Resampling.LANCZOS)

        return img
    except Exception as e:
        return None

@app.route("/admin/products/add", methods=["GET", "POST"], endpoint='admin_add_product')
@admin_required
def admin_add_product():
    if request.method == "POST":
        name = request.form["name"]
        desc = request.form["description"]
        price = request.form["price"]
        stock = request.form["stock"]
        category_id = request.form.get("category_id") or None
        service_id = request.form.get("service_id") or None
        image_url = request.form.get("image_url", "")
        image_file = request.files.get("image_file")

        image_path = None

        # Handle image upload
        if image_file and image_file.filename and allowed_file(image_file.filename):
            # Create uploads directory if it doesn't exist
            upload_dir = os.path.join(app.static_folder, 'images', 'products')
            os.makedirs(upload_dir, exist_ok=True)

            # Generate unique filename
            file_extension = image_file.filename.rsplit('.', 1)[1].lower()
            filename = f"{uuid.uuid4()}.{file_extension}"
            filepath = os.path.join(upload_dir, filename)

            # Process and save image
            processed_img = process_image(image_file)
            if processed_img:
                processed_img.save(filepath, quality=85, optimize=True)
                image_path = f"images/products/{filename}"
            else:
                flash("Грешка при обработката на изображението.")
                return redirect(url_for("admin_add_product"))

        elif image_url:
            # Use the provided URL
            image_path = image_url

        db = get_db()
        cursor = db.cursor()
        try:
            cursor.execute(
                "INSERT INTO products (name, description, price, stock, category_id, service_id, image) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (name, desc, price, stock, category_id, service_id, image_path)
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
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page

    db = get_db()
    cursor = db.cursor(dictionary=True)

    # Get total count
    cursor.execute("SELECT COUNT(*) as total FROM products")
    total = cursor.fetchone()['total']

    # Get paginated results with category and service names
    cursor.execute("""
        SELECT p.*, c.name as category_name, s.name as service_name
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        LEFT JOIN services s ON p.service_id = s.id
        LIMIT %s OFFSET %s
    """, (per_page, offset))
    products = cursor.fetchall()

    # Calculate pagination info
    total_pages = (total + per_page - 1) // per_page
    has_prev = page > 1
    has_next = page < total_pages

    return render_template("admin_products.html",
                         products=products,
                         page=page,
                         total_pages=total_pages,
                         has_prev=has_prev,
                         has_next=has_next)

@app.route("/admin/categories", endpoint='admin_categories')
@admin_required
def admin_categories():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page

    db = get_db()
    cursor = db.cursor(dictionary=True)

    # Get total count
    cursor.execute("SELECT COUNT(*) as total FROM categories")
    total = cursor.fetchone()['total']

    # Get paginated results
    cursor.execute("SELECT * FROM categories LIMIT %s OFFSET %s", (per_page, offset))
    categories = cursor.fetchall()

    # Calculate pagination info
    total_pages = (total + per_page - 1) // per_page
    has_prev = page > 1
    has_next = page < total_pages

    return render_template("admin_categories.html",
                         categories=categories,
                         page=page,
                         total_pages=total_pages,
                         has_prev=has_prev,
                         has_next=has_next)

@app.route("/admin/categories/add", methods=["POST"], endpoint='admin_add_category')
@admin_required
def admin_add_category():
    name = request.form["name"]
    slug = request.form["slug"]
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("INSERT INTO categories (name, slug) VALUES (%s, %s)", (name, slug))
        db.commit()
        flash("Category added successfully.")
    except mysql.connector.Error as err:
        db.rollback()
        flash(f"Error adding category: {err}")
    return redirect(url_for("admin_categories"))

@app.route("/admin/categories/edit/<int:category_id>", methods=["GET", "POST"], endpoint='admin_edit_category')
@admin_required
def admin_edit_category(category_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)

    if request.method == "POST":
        name = request.form["name"]
        slug = request.form["slug"]
        try:
            cursor.execute("UPDATE categories SET name=%s, slug=%s WHERE id=%s", (name, slug, category_id))
            db.commit()
            flash("Category updated successfully.")
            return redirect(url_for("admin_categories"))
        except mysql.connector.Error as err:
            db.rollback()
            flash(f"Error updating category: {err}")

    cursor.execute("SELECT * FROM categories WHERE id=%s", (category_id,))
    category = cursor.fetchone()
    if not category:
        flash("Category not found.")
        return redirect(url_for("admin_categories"))

    return render_template("admin_edit_category.html", category=category)

@app.route("/admin/categories/delete/<int:category_id>", endpoint='admin_delete_category')
@admin_required
def admin_delete_category(category_id):
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("DELETE FROM categories WHERE id=%s", (category_id,))
        db.commit()
        flash("Category deleted.")
    except mysql.connector.Error as err:
        db.rollback()
        flash(f"Error deleting category: {err}")
    return redirect(url_for("admin_categories"))

@app.route("/admin/services", endpoint='admin_services')
@admin_required
def admin_services():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page

    db = get_db()
    cursor = db.cursor(dictionary=True)

    # Get total count
    cursor.execute("SELECT COUNT(*) as total FROM services")
    total = cursor.fetchone()['total']

    # Get paginated results
    cursor.execute("SELECT * FROM services LIMIT %s OFFSET %s", (per_page, offset))
    services = cursor.fetchall()

    # Calculate pagination info
    total_pages = (total + per_page - 1) // per_page
    has_prev = page > 1
    has_next = page < total_pages

    return render_template("admin_services.html",
                         services=services,
                         page=page,
                         total_pages=total_pages,
                         has_prev=has_prev,
                         has_next=has_next)

@app.route("/admin/services/add", methods=["POST"], endpoint='admin_add_service')
@admin_required
def admin_add_service():
    name = request.form["name"]
    slug = request.form["slug"]
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("INSERT INTO services (name, slug) VALUES (%s, %s)", (name, slug))
        db.commit()
        flash("Service added successfully.")
    except mysql.connector.Error as err:
        db.rollback()
        flash(f"Error adding service: {err}")
    return redirect(url_for("admin_services"))

@app.route("/admin/services/edit/<int:service_id>", methods=["GET", "POST"], endpoint='admin_edit_service')
@admin_required
def admin_edit_service(service_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)

    if request.method == "POST":
        name = request.form["name"]
        slug = request.form["slug"]
        try:
            cursor.execute("UPDATE services SET name=%s, slug=%s WHERE id=%s", (name, slug, service_id))
            db.commit()
            flash("Service updated successfully.")
            return redirect(url_for("admin_services"))
        except mysql.connector.Error as err:
            db.rollback()
            flash(f"Error updating service: {err}")

    cursor.execute("SELECT * FROM services WHERE id=%s", (service_id,))
    service = cursor.fetchone()
    if not service:
        flash("Service not found.")
        return redirect(url_for("admin_services"))

    return render_template("admin_edit_service.html", service=service)

@app.route("/admin/services/delete/<int:service_id>", endpoint='admin_delete_service')
@admin_required
def admin_delete_service(service_id):
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("DELETE FROM services WHERE id=%s", (service_id,))
        db.commit()
        flash("Service deleted.")
    except mysql.connector.Error as err:
        db.rollback()
        flash(f"Error deleting service: {err}")
    return redirect(url_for("admin_services"))

@app.route("/admin/orders", endpoint='admin_orders')
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

@app.route("/admin/orders/<int:order_id>", endpoint='admin_order_detail')
@admin_required
def admin_order_detail(order_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("""
        SELECT oi.quantity, oi.price, p.name
        FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        WHERE oi.order_id = %s
    """, (order_id,))
    items = cursor.fetchall()
    return render_template("admin_folder_detail.html", items=items, order_id=order_id)

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

@app.route("/admin/users/add", methods=["POST"], endpoint='admin_add_user')
@admin_required
def admin_add_user():
    username = request.form["username"]
    password = request.form["password"]
    realname = request.form.get("realname", "")
    role = request.form.get("role", "customer")

    password_hash = generate_password_hash(password)

    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute(
            "INSERT INTO users (username, password_hash, realname, role) VALUES (%s, %s, %s, %s)",
            (username, password_hash, realname, role)
        )
        db.commit()
        flash("User added successfully.")
    except mysql.connector.Error as err:
        db.rollback()
        flash(f"Error adding user: {err}")
    return redirect(url_for("admin_users"))

@app.route("/admin/users/edit/<int:user_id>", methods=["GET", "POST"], endpoint='admin_edit_user')
@admin_required
def admin_edit_user(user_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)

    if request.method == "POST":
        username = request.form["username"]
        realname = request.form.get("realname", "")
        role = request.form.get("role", "customer")
        try:
            cursor.execute("UPDATE users SET username=%s, realname=%s, role=%s WHERE id=%s", (username, realname, role, user_id))
            db.commit()
            flash("User updated successfully.")
            return redirect(url_for("admin_users"))
        except mysql.connector.Error as err:
            db.rollback()
            flash(f"Error updating user: {err}")

    cursor.execute("SELECT * FROM users WHERE id=%s", (user_id,))
    user = cursor.fetchone()
    if not user:
        flash("User not found.")
        return redirect(url_for("admin_users"))

    return render_template("admin_edit_user.html", user=user)

@app.route("/admin/users/delete/<int:user_id>", endpoint='admin_delete_user')
@admin_required
def admin_delete_user(user_id):
    # Don't allow deletion of the current logged-in user
    if user_id == session.get("user_id"):
        flash("You cannot delete your own account.")
        return redirect(url_for("admin_users"))

    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("DELETE FROM users WHERE id=%s", (user_id,))
        db.commit()
        flash("User deleted successfully.")
    except mysql.connector.Error as err:
        db.rollback()
        flash(f"Error deleting user: {err}")
    return redirect(url_for("admin_users"))

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

@app.route("/admin/products/edit/<int:product_id>", methods=["GET", "POST"], endpoint='admin_edit_product')
@admin_required
def admin_edit_product(product_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)

    if request.method == "POST":
        name = request.form["name"]
        desc = request.form["description"]
        price = request.form["price"]
        stock = request.form["stock"]
        category_id = request.form.get("category_id") or None
        service_id = request.form.get("service_id") or None
        image_url = request.form.get("image_url", "")
        image_file = request.files.get("image_file")

        image_path = None
        current_image = request.form.get("current_image", "")

        # Handle image upload
        if image_file and image_file.filename and allowed_file(image_file.filename):
            upload_dir = os.path.join(app.static_folder, 'images', 'products')
            os.makedirs(upload_dir, exist_ok=True)

            file_extension = image_file.filename.rsplit('.', 1)[1].lower()
            filename = f"{uuid.uuid4()}.{file_extension}"
            filepath = os.path.join(upload_dir, filename)

            processed_img = process_image(image_file)
            if processed_img:
                processed_img.save(filepath, quality=85, optimize=True)
                image_path = f"images/products/{filename}"
            else:
                flash("Грешка при обработката на изображението.")
                return redirect(url_for("admin_edit_product", product_id=product_id))
        elif image_url:
            image_path = image_url
        else:
            image_path = current_image

        try:
            cursor.execute(
                "UPDATE products SET name=%s, description=%s, price=%s, stock=%s, category_id=%s, service_id=%s, image=%s WHERE id=%s",
                (name, desc, price, stock, category_id, service_id, image_path, product_id)
            )
            db.commit()
            flash("Product updated successfully.")
            return redirect(url_for("admin_products"))
        except mysql.connector.Error as err:
            db.rollback()
            flash(f"Error updating product: {err}")

    cursor.execute("SELECT * FROM products WHERE id=%s", (product_id,))
    product = cursor.fetchone()
    if not product:
        flash("Product not found.")
        return redirect(url_for("admin_products"))

    return render_template("admin_edit_product.html", product=product)

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
