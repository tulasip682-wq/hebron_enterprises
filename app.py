from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os

from models import db, Admin, User, Category, Product, Inquiry
app = Flask(__name__, static_folder="static")

app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "hebron_super_secure_secret_key")

database_url = os.environ.get("DATABASE_URL")
if database_url:
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
elif os.environ.get("VERCEL"):
    import shutil
    tmp_db = "/tmp/database.db"
    if not os.path.exists(tmp_db):
        for candidate in ["instance/database.db", "database.db"]:
            if os.path.exists(candidate):
                try:
                    shutil.copyfile(candidate, tmp_db)
                    break
                except Exception:
                    pass
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{tmp_db}"
else:
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

if os.environ.get("VERCEL"):
    app.config["UPLOAD_FOLDER"] = "/tmp/uploads"
else:
    app.config["UPLOAD_FOLDER"] = "static/uploads"

app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB

db.init_app(app)

# ---------------- IMAGE VALIDATION ----------------
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

def allowed_file(filename):
    return (
        "." in filename and
        filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )

# ---------------- CREATE FOLDERS ----------------
try:
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs("static/images", exist_ok=True)
except OSError:
    pass

# ---------------- CONTEXT PROCESSOR ----------------
@app.context_processor
def inject_now():
    return {"now": datetime.utcnow()}

# ---------------- ERROR HANDLERS ----------------
@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404


@app.errorhandler(500)
def server_error(e):
    return render_template("500.html"), 500

# ---------------- CUSTOMER ROUTES ----------------

@app.route("/")
def home():
    products = Product.query.order_by(Product.id.desc()).limit(3).all()
    categories = Category.query.all()

    return render_template(
        "home.html",
        products=products,
        categories=categories
    )


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/products")
def products():

    category_id = request.args.get("category")
    search_query = request.args.get("search")

    query = Product.query

    if category_id:
        query = query.filter(Product.category_id == category_id)

    if search_query:
        query = query.filter(
            (Product.product_name.like(f"%{search_query}%")) |
            (Product.brand.like(f"%{search_query}%")) |
            (Product.model_number.like(f"%{search_query}%")) |
            (Product.description.like(f"%{search_query}%"))
        )

    products_list = query.all()
    categories_list = Category.query.all()

    return render_template(
        "products.html",
        products=products_list,
        categories=categories_list,
        selected_category=category_id,
        search_query=search_query
    )


@app.route("/product/<int:id>")
def product_details(id):

    product = Product.query.get_or_404(id)

    related_products = Product.query.filter(
        Product.category_id == product.category_id,
        Product.id != product.id
    ).limit(3).all()

    return render_template(
        "product_details.html",
        product=product,
        related_products=related_products
    )


@app.route("/contact", methods=["GET", "POST"])
def contact():

    if session.get("role") != "user":
        flash("Please login to send an inquiry.", "warning")
        return redirect(url_for("user_login"))

    prefill_msg = ""
    product_id = request.args.get("product_id")

    if product_id and product_id.isdigit():
        prod = Product.query.get(int(product_id))
        if prod:
            prefill_msg = (
                f"Hello Hebron Enterprises, I would like to receive a quotation "
                f"for {prod.product_name} "
                f"(Model: {prod.model_number}, Brand: {prod.brand})."
            )

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        message = request.form.get("message", "").strip()

        if not name or not email or not message:
            flash(
                "Please fill in all required fields.",
                "danger"
            )

            return render_template(
                "contact.html",
                name=name,
                email=email,
                phone=phone,
                message=message,
                prefill_msg=prefill_msg
            )

        inquiry = Inquiry(
        name=name,
        email=email,
        phone=phone,
        message=message,
        status="New",
        created_at=datetime.utcnow(),
        user_id=session.get("user_id")
)

        try:
            db.session.add(inquiry)
            db.session.commit()

            flash(
                "Thank you! Your inquiry has been submitted successfully.",
                "success"
            )

            return redirect(url_for("contact"))

        except Exception:
            db.session.rollback()

            flash(
                "Database error. Please try again later.",
                "danger"
            )

    return render_template(
        "contact.html",
        prefill_msg=prefill_msg
    )
    # ---------------- ADMIN REGISTER ----------------

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if not username or not password:
            flash("All fields are required.", "danger")
            return redirect(url_for("register"))

        exists = Admin.query.filter_by(username=username).first()

        if exists:
            flash("Username already exists.", "danger")
            return redirect(url_for("register"))

        new_admin = Admin(
            username=username,
            password=generate_password_hash(password)
        )

        try:
            db.session.add(new_admin)
            db.session.commit()

            flash(
                "Admin registered successfully. Please login.",
                "success"
            )

            return redirect(url_for("login"))

        except Exception:
            db.session.rollback()
            flash("Database error.", "danger")

    return render_template("register.html")

# ---------------- USER REGISTER ----------------

@app.route("/user_register", methods=["GET", "POST"])
def user_register():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        if not username or not email or not password:
            flash("All fields are required.", "danger")
            return redirect(url_for("user_register"))

        existing = User.query.filter_by(username=username).first()
        if existing:
            flash("Username already exists.", "danger")
            return redirect(url_for("user_register"))

        existing_email = User.query.filter_by(email=email).first()
        if existing_email:
            flash("Email already registered.", "danger")
            return redirect(url_for("user_register"))

        user = User(
            username=username,
            email=email,
            password=generate_password_hash(password)
        )

        try:
            db.session.add(user)
            db.session.commit()
            flash("Registration successful. Please login.", "success")
            return redirect(url_for("user_login"))
        except Exception:
            db.session.rollback()
            flash("Database error. Please try again.", "danger")
            return redirect(url_for("user_register"))

    return render_template("user_register.html")


# ---------------- ADMIN LOGIN ----------------

@app.route("/login", methods=["GET", "POST"])
def login():

    if "admin" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if not username or not password:
            flash("Please enter both username and password.", "danger")
            return render_template("login.html", username=username)

        admin = Admin.query.filter_by(username=username).first()

        if admin and check_password_hash(admin.password, password):

            session["admin"] = admin.username
            session["role"] = "admin"

            flash("Successfully logged in as Admin.", "success")
            return redirect(url_for("dashboard"))

        flash("Invalid Username or Password.", "danger")

    return render_template("login.html")

# ---------------- USER LOGIN ----------------

@app.route("/user_login", methods=["GET","POST"])
def user_login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):

            session["role"] = "user"
            session["user"] = user.username
            session["user_id"] = user.id

            return redirect(url_for("user_dashboard"))

        flash("Invalid Username or Password.", "danger")

    return render_template("user_login.html")


# ---------------- LOGOUT ----------------

@app.route("/logout")
def logout():

    session.clear()

    flash(
        "You have logged out successfully.",
        "success"
    )

    return redirect(url_for("home"))


# ---------------- DASHBOARD ----------------

@app.route("/dashboard")
def dashboard():

    if "admin" not in session:
        flash("Access Denied.", "danger")
        return redirect(url_for("login"))

    total_products = Product.query.count()
    total_categories = Category.query.count()
    total_inquiries = Inquiry.query.count()

    latest_inquiries = Inquiry.query.order_by(
        Inquiry.created_at.desc()
    ).limit(5).all()

    return render_template(
        "dashboard.html",
        total_products=total_products,
        total_categories=total_categories,
        total_inquiries=total_inquiries,
        latest_inquiries=latest_inquiries
    )

@app.route("/user_dashboard")
def user_dashboard():

    if session.get("role") != "user":
        return redirect(url_for("user_login"))

    inquiries = Inquiry.query.filter_by(
        user_id=session["user_id"]
    ).all()

    return render_template(
        "user_dashboard.html",
        inquiries=inquiries
    )

# ---------------- CATEGORY CRUD ----------------

@app.route("/categories")
def categories():

    if "admin" not in session:
        flash("Access Denied.", "danger")
        return redirect(url_for("login"))

    categories_list = Category.query.all()

    return render_template(
        "categories.html",
        categories=categories_list
    )


@app.route("/add_category", methods=["GET", "POST"])
def add_category():

    if "admin" not in session:
        flash("Access Denied.", "danger")
        return redirect(url_for("login"))

    if request.method == "POST":

        category_name = request.form.get(
            "category_name",
            ""
        ).strip()

        description = request.form.get(
            "description",
            ""
        ).strip()

        if not category_name:
            flash(
                "Category name is required.",
                "danger"
            )

            return render_template(
                "add_category.html",
                description=description
            )

        exists = Category.query.filter_by(
            category_name=category_name
        ).first()

        if exists:
            flash(
                "Category already exists.",
                "danger"
            )

            return render_template(
                "add_category.html",
                category_name=category_name,
                description=description
            )

        category = Category(
            category_name=category_name,
            description=description
        )

        try:
            db.session.add(category)
            db.session.commit()

            flash(
                "Category added successfully.",
                "success"
            )

            return redirect(url_for("categories"))

        except Exception:
            db.session.rollback()

            flash(
                "Database error.",
                "danger"
            )

    return render_template("add_category.html")


@app.route("/edit_category/<int:id>", methods=["GET", "POST"])
def edit_category(id):

    if "admin" not in session:
        flash("Access Denied.", "danger")
        return redirect(url_for("login"))

    category = Category.query.get_or_404(id)

    if request.method == "POST":

        category_name = request.form.get(
            "category_name",
            ""
        ).strip()

        description = request.form.get(
            "description",
            ""
        ).strip()

        if not category_name:
            flash(
                "Category name is required.",
                "danger"
            )

            return render_template(
                "edit_category.html",
                category=category
            )

        exists = Category.query.filter_by(
            category_name=category_name
        ).first()

        if exists and exists.id != category.id:
            flash(
                "Category already exists.",
                "danger"
            )

            return render_template(
                "edit_category.html",
                category=category
            )

        category.category_name = category_name
        category.description = description

        try:
            db.session.commit()

            flash(
                "Category updated successfully.",
                "success"
            )

            return redirect(url_for("categories"))

        except Exception:
            db.session.rollback()

            flash(
                "Database error.",
                "danger"
            )

    return render_template(
        "edit_category.html",
        category=category
    )


@app.route("/delete_category/<int:id>")
def delete_category(id):

    if "admin" not in session:
        flash("Access Denied.", "danger")
        return redirect(url_for("login"))

    category = Category.query.get_or_404(id)

    if len(category.products) > 0:

        flash(
            "Cannot delete a category that contains products.",
            "danger"
        )

        return redirect(url_for("categories"))

    try:
        db.session.delete(category)
        db.session.commit()

        flash(
            "Category deleted successfully.",
            "success"
        )

    except Exception:
        db.session.rollback()

        flash(
            "Database error.",
            "danger"
        )

    return redirect(url_for("categories"))
    # ---------------- PRODUCT CRUD ----------------

@app.route("/admin_products")
def admin_products():
    if "admin" not in session:
        flash("Access Denied.", "danger")
        return redirect(url_for("login"))

    products_list = Product.query.all()

    return render_template(
        "admin_products.html",
        products=products_list
    )


@app.route("/add_product", methods=["GET", "POST"])
def add_product():

    if "admin" not in session:
        flash("Access Denied.", "danger")
        return redirect(url_for("login"))

    categories_list = Category.query.all()

    if request.method == "POST":

        product_name = request.form.get("product_name", "").strip()
        brand = request.form.get("brand", "").strip()
        model_number = request.form.get("model_number", "").strip()
        description = request.form.get("description", "").strip()
        category_id = request.form.get("category_id")
        stock = request.form.get("stock", "").strip()
        image_file = request.files.get("image")

        if not product_name or not brand or not model_number or not category_id or stock == "":
            flash("Please fill in all required fields.", "danger")
            return render_template(
                "add_product.html",
                categories=categories_list,
                product_name=product_name,
                brand=brand,
                model_number=model_number,
                description=description,
                stock=stock
            )

        try:
            stock_val = int(stock)
            if stock_val < 0:
                raise ValueError
        except ValueError:
            flash("Stock must be a non-negative integer.", "danger")
            return render_template(
                "add_product.html",
                categories=categories_list,
                product_name=product_name,
                brand=brand,
                model_number=model_number,
                description=description,
                stock=stock
            )

        filename = ""

        if image_file and image_file.filename != "":

            if not allowed_file(image_file.filename):
                flash(
                    "Only PNG, JPG, JPEG and WEBP images are allowed.",
                    "danger"
                )

                return render_template(
                    "add_product.html",
                    categories=categories_list
                )

            filename = secure_filename(image_file.filename)

            timestamp = datetime.now().strftime("%Y%m%d%H%M%S_")
            filename = timestamp + filename

            image_file.save(
                os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    filename
                )
            )

        product = Product(
            product_name=product_name,
            brand=brand,
            model_number=model_number,
            description=description,
            category_id=category_id,
            image=filename,
            stock=stock_val
        )

        try:
            db.session.add(product)
            db.session.commit()

            flash(
                "Product added successfully.",
                "success"
            )

            return redirect(url_for("admin_products"))

        except Exception:
            db.session.rollback()

            flash(
                "Database error.",
                "danger"
            )

    return render_template(
        "add_product.html",
        categories=categories_list
    )


@app.route("/edit_product/<int:id>", methods=["GET", "POST"])
def edit_product(id):

    if "admin" not in session:
        flash("Access Denied.", "danger")
        return redirect(url_for("login"))

    product = Product.query.get_or_404(id)
    categories_list = Category.query.all()

    if request.method == "POST":

        product_name = request.form.get("product_name", "").strip()
        brand = request.form.get("brand", "").strip()
        model_number = request.form.get("model_number", "").strip()
        description = request.form.get("description", "").strip()
        category_id = request.form.get("category_id")
        stock = request.form.get("stock", "").strip()
        image_file = request.files.get("image")

        if not product_name or not brand or not model_number or not category_id or stock == "":
            flash("Please fill in all required fields.", "danger")

            return render_template(
                "edit_product.html",
                product=product,
                categories=categories_list
            )

        try:
            stock_val = int(stock)
            if stock_val < 0:
                raise ValueError
        except ValueError:
            flash("Stock must be a non-negative integer.", "danger")
            return render_template(
                "edit_product.html",
                product=product,
                categories=categories_list
            )

        if image_file and image_file.filename != "":

            if not allowed_file(image_file.filename):
                flash(
                    "Only PNG, JPG, JPEG and WEBP images are allowed.",
                    "danger"
                )

                return render_template(
                    "edit_product.html",
                    product=product,
                    categories=categories_list
                )

            filename = secure_filename(image_file.filename)

            timestamp = datetime.now().strftime("%Y%m%d%H%M%S_")
            filename = timestamp + filename

            image_file.save(
                os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    filename
                )
            )

            if product.image:
                old_path = os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    product.image
                )

                if os.path.exists(old_path):
                    try:
                        os.remove(old_path)
                    except OSError:
                        pass

            product.image = filename

        product.product_name = product_name
        product.brand = brand
        product.model_number = model_number
        product.description = description
        product.category_id = category_id
        product.stock = stock_val

        try:
            db.session.commit()

            flash(
                "Product updated successfully.",
                "success"
            )

            return redirect(url_for("admin_products"))

        except Exception:
            db.session.rollback()

            flash(
                "Database error.",
                "danger"
            )

    return render_template(
        "edit_product.html",
        product=product,
        categories=categories_list
    )


@app.route("/delete_product/<int:id>")
def delete_product(id):

    if "admin" not in session:
        flash("Access Denied.", "danger")
        return redirect(url_for("login"))

    product = Product.query.get_or_404(id)

    if product.image:
        image_path = os.path.join(
            app.config["UPLOAD_FOLDER"],
            product.image
        )

        if os.path.exists(image_path):
            try:
                os.remove(image_path)
            except OSError:
                pass

    try:
        db.session.delete(product)
        db.session.commit()

        flash(
            "Product deleted successfully.",
            "success"
        )

    except Exception:
        db.session.rollback()

        flash(
            "Database error.",
            "danger"
        )

    return redirect(url_for("admin_products"))
    # ---------------- INQUIRIES CRUD ----------------

@app.route("/admin_inquiries")
def admin_inquiries():

    if "admin" not in session:
        flash("Access Denied.", "danger")
        return redirect(url_for("login"))

    inquiries_list = Inquiry.query.order_by(
        Inquiry.created_at.desc()
    ).all()

    return render_template(
        "admin_inquiries.html",
        inquiries=inquiries_list
    )


@app.route("/update_inquiry/<int:id>")
def update_inquiry(id):

    if "admin" not in session:
        flash("Access Denied.", "danger")
        return redirect(url_for("login"))

    inquiry = Inquiry.query.get_or_404(id)
    inquiry.status = "Replied"

    try:
        db.session.commit()

        flash(
            "Inquiry marked as Replied.",
            "success"
        )

    except Exception:
        db.session.rollback()

        flash(
            "Database error.",
            "danger"
        )

    return redirect(url_for("admin_inquiries"))


@app.route("/delete_inquiry/<int:id>")
def delete_inquiry(id):

    if "admin" not in session:
        flash("Access Denied.", "danger")
        return redirect(url_for("login"))

    inquiry = Inquiry.query.get_or_404(id)

    try:
        db.session.delete(inquiry)
        db.session.commit()

        flash(
            "Inquiry deleted successfully.",
            "success"
        )

    except Exception:
        db.session.rollback()

        flash(
            "Database error.",
            "danger"
        )

    return redirect(url_for("admin_inquiries"))


# ---------------- INITIAL DATA ----------------

def create_default_admin():

    admin = Admin.query.filter_by(username="admin").first()

    if not admin:

        default_admin = Admin(
            username="admin",
            password=generate_password_hash("admin123")
        )

        db.session.add(default_admin)
        db.session.commit()


def create_default_categories():

    categories = [
        (
            "Domestic Pumps",
            "Home water supply, overhead tank, and domestic pressure boosting pump solutions."
        ),
        (
            "Agricultural Pumps",
            "Heavy-duty farm and crops irrigation pumps including borehole submersibles."
        ),
        (
            "Industrial Pumps",
            "High capacity centrifugal, multistage, and chemical drainage pump systems."
        ),
        (
            "Solar Pumps",
            "Eco-friendly, energy saving solar powered borehole and surface water management pumps."
        )
    ]

    for name, description in categories:

        exists = Category.query.filter_by(
            category_name=name
        ).first()

        if not exists:

            db.session.add(
                Category(
                    category_name=name,
                    description=description
                )
            )

    db.session.commit()


def create_default_products():

    domestic = Category.query.filter_by(
        category_name="Domestic Pumps"
    ).first()

    agricultural = Category.query.filter_by(
        category_name="Agricultural Pumps"
    ).first()

    industrial = Category.query.filter_by(
        category_name="Industrial Pumps"
    ).first()

    solar = Category.query.filter_by(
        category_name="Solar Pumps"
    ).first()

    if Product.query.count() == 0:

        products = [

            Product(
                product_name="CRI Self-Priming Regenerative Monoblock Pump",
                brand="CRI",
                model_number="REGEN-1",
                description="Compact self-priming monoblock pump suitable for domestic water supply, pressure boosting, gardens, apartments, and overhead tank filling.",
                image="monoblock_pump.png",
                category_id=domestic.id,
                stock=10
            ),

            Product(
                product_name="CRI Pressure Booster Pump",
                brand="CRI",
                model_number="PB-200",
                description="Automatic pressure booster pump designed for homes, villas, apartments, and commercial buildings with consistent water pressure.",
                image="booster_pump.png",
                category_id=domestic.id,
                stock=10
            ),

            Product(
                product_name="CRI Water-Filled Borewell Submersible Pump",
                brand="CRI",
                model_number="V4-AGRI",
                description="High-efficiency borewell submersible pump for agricultural irrigation, farms, plantations, and groundwater extraction.",
                image="borewell_pump.png",
                category_id=agricultural.id,
                stock=10
            ),

            Product(
                product_name="CRI Openwell Submersible Pump",
                brand="CRI",
                model_number="OW-500",
                description="Reliable openwell submersible pump for irrigation, water transfer, and community water supply applications.",
                image="openwell_pump.png",
                category_id=agricultural.id,
                stock=10
            ),

            Product(
                product_name="CRI Horizontal End-Suction Centrifugal Pump",
                brand="CRI",
                model_number="IND-CENT-50",
                description="Heavy-duty centrifugal pump for industrial water circulation, cooling systems, factories, and process industries.",
                image="centrifugal_pump.png",
                category_id=industrial.id,
                stock=10
            ),

            Product(
                product_name="CRI Vertical Multistage Pump",
                brand="CRI",
                model_number="VM-750",
                description="Vertical multistage pressure pump suitable for commercial buildings, RO plants, hotels, hospitals, and boiler feed systems.",
                image="multistage_pump.png",
                category_id=industrial.id,
                stock=10
            ),

            Product(
                product_name="CRI Solar Powered Borewell Pump Set",
                brand="CRI",
                model_number="SOLAR-V6",
                description="Energy-efficient solar pumping solution for farms, villages, and remote areas without reliable electricity.",
                image="solar_pump.png",
                category_id=solar.id,
                stock=10
            )

        ]

        db.session.add_all(products)
        db.session.commit()


# ---------------- INITIALIZE DATABASE ----------------
with app.app_context():
    try:
        db.create_all()
        create_default_admin()
        create_default_categories()
        create_default_products()
    except Exception as e:
        app.logger.warning(f"Database auto-init notification: {e}")

# ---------------- MAIN ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)