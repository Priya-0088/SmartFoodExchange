
import os
from functools import wraps
from datetime import datetime

from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, session
)

from flask_bcrypt import Bcrypt
from db import get_db_connection


# ==========================================
# 1. FLASK CONFIGURATION
# ==========================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "foodbridge-development-secret-key"
)

bcrypt = Bcrypt(app)


# ==========================================
# 2. DATABASE HELPER
# ==========================================

def close_database(connection, cursor):
    if cursor:
        cursor.close()

    if connection and connection.is_connected():
        connection.close()


# ==========================================
# 3. ROLE-BASED ACCESS CONTROL
# ==========================================

def role_required(required_role):

    def decorator(function):

        @wraps(function)
        def wrapper(*args, **kwargs):

            if "user_id" not in session:
                flash("Please login to continue.")
                return redirect(url_for("login"))

            if session.get("role") != required_role:
                flash("You are not authorized to access this page.")
                return redirect(url_for("login"))

            return function(*args, **kwargs)

        return wrapper

    return decorator


# ==========================================
# 4. HOME PAGE
# ==========================================

@app.route("/")
def home():
    return render_template("index.html")


# ==========================================
# 5. USER REGISTRATION
# ==========================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        phone = request.form.get("phone", "").strip() or None
        address = request.form.get("address", "").strip() or None
        city = request.form.get("city", "").strip() or None

        role = request.form.get("role", "")

        if not full_name or not email or not password:
            flash("Please fill in all required fields.")
            return redirect(url_for("register"))

        if len(password) < 8:
            flash("Password must contain at least 8 characters.")
            return redirect(url_for("register"))

        if role not in ("DONOR", "NGO"):
            flash("Please select a valid account type.")
            return redirect(url_for("register"))

        if role == "DONOR":

            donor_type = request.form.get("donor_type", "")

            organization_name = (
                request.form.get("donor_organization", "").strip() or None
            )

            if donor_type not in (
                "RESTAURANT", "SUPERMARKET", "HOTEL", "INDIVIDUAL"
            ):
                flash("Please select a valid donor type.")
                return redirect(url_for("register"))

        else:

            organization_name = request.form.get(
                "organization_name", ""
            ).strip()

            registration_number = request.form.get(
                "registration_number", ""
            ).strip() or None

            service_area = request.form.get(
                "service_area", ""
            ).strip() or None

            if not organization_name:
                flash("Please enter your organization name.")
                return redirect(url_for("register"))

        hashed_password = bcrypt.generate_password_hash(
            password
        ).decode("utf-8")

        connection = None
        cursor = None

        try:
            connection = get_db_connection()
            cursor = connection.cursor()

            cursor.execute(
                "SELECT user_id FROM users WHERE email = %s",
                (email,)
            )

            if cursor.fetchone():
                flash("This email is already registered.")
                return redirect(url_for("register"))

            cursor.execute("""
                INSERT INTO users
                (full_name, email, password, phone, address, city, role)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                full_name, email, hashed_password,
                phone, address, city, role
            ))

            user_id = cursor.lastrowid

            if role == "DONOR":

                cursor.execute("""
                    INSERT INTO donor_profiles
                    (user_id, organization_name, donor_type)
                    VALUES (%s, %s, %s)
                """, (
                    user_id, organization_name, donor_type
                ))

            else:

                cursor.execute("""
                    INSERT INTO ngo_profiles
                    (user_id, organization_name,
                     registration_number, service_area)
                    VALUES (%s, %s, %s, %s)
                """, (
                    user_id, organization_name,
                    registration_number, service_area
                ))

            connection.commit()

            flash("Registration successful! Please login.")
            return redirect(url_for("login"))

        except Exception as e:
            if connection:
                connection.rollback()

            print("Registration error:", e)
            flash("Registration failed. Please try again.")

        finally:
            close_database(connection, cursor)

    return render_template("register.html")


# ==========================================
# 6. USER LOGIN
# ==========================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        connection = None
        cursor = None

        try:
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)

            cursor.execute(
                "SELECT * FROM users WHERE email = %s",
                (email,)
            )

            user = cursor.fetchone()

            if user and bcrypt.check_password_hash(
                user["password"], password
            ):

                session.clear()

                session["user_id"] = user["user_id"]
                session["full_name"] = user["full_name"]
                session["role"] = user["role"]

                if user["role"] == "DONOR":
                    return redirect(url_for("donor_dashboard"))

                if user["role"] == "NGO":
                    return redirect(url_for("ngo_dashboard"))

                if user["role"] == "ADMIN":
                    return redirect(url_for("admin_dashboard"))

            flash("Invalid email or password.")

        except Exception as e:
            print("Login error:", e)
            flash("Something went wrong. Please try again.")

        finally:
            close_database(connection, cursor)

    return render_template("login.html")


# ==========================================
# 7. DONOR DASHBOARD
# ==========================================

@app.route("/donor-dashboard")
@role_required("DONOR")
def donor_dashboard():

    # IMPORTANT: Separate donor template
    return render_template("donor_dashboard.html")


# ==========================================
# 8. NGO DASHBOARD
# ==========================================

@app.route("/ngo-dashboard")
@role_required("NGO")
def ngo_dashboard():

    # IMPORTANT: Separate NGO template
    return render_template("ngo_dashboard.html")


# ==========================================
# 9. ADMIN DASHBOARD
# ==========================================

@app.route("/admin-dashboard")
@role_required("ADMIN")
def admin_dashboard():
    return render_template("dashboard.html")


# ==========================================
# 10. DONATE FOOD
# ==========================================

@app.route("/add-food", methods=["GET", "POST"])
@role_required("DONOR")
def add_food():

    connection = None
    cursor = None
    categories = []

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT category_id, category_name
            FROM food_categories
            ORDER BY category_name
        """)

        categories = cursor.fetchall()

        if request.method == "POST":

            food_name = request.form.get("food_name", "").strip()
            category_id = request.form.get("category_id", "")
            description = request.form.get("description", "").strip() or None

            quantity_text = request.form.get("quantity", "")
            unit = request.form.get("unit", "")

            prepared_text = request.form.get("prepared_at", "").strip()
            expiry_text = request.form.get("expiry_at", "").strip()

            pickup_address = request.form.get(
                "pickup_address", ""
            ).strip()

            city = request.form.get("city", "").strip()

            if not all([
                food_name, category_id, quantity_text,
                unit, expiry_text, pickup_address, city
            ]):
                flash("Please fill in all required fields.")
                return render_template(
                    "add_food.html", categories=categories
                )

            try:
                category_id = int(category_id)
                quantity = float(quantity_text)

                if quantity <= 0:
                    raise ValueError

            except ValueError:
                flash("Please enter a valid category and quantity.")
                return render_template(
                    "add_food.html", categories=categories
                )

            if not any(
                int(c["category_id"]) == category_id for c in categories
            ):
                flash("Please select a valid food category.")
                return render_template(
                    "add_food.html", categories=categories
                )

            if unit not in ("KG", "LITRE", "PACKETS", "PLATES"):
                flash("Please select a valid unit.")
                return render_template(
                    "add_food.html", categories=categories
                )

            try:
                expiry_at = datetime.strptime(
                    expiry_text, "%Y-%m-%dT%H:%M"
                )

                prepared_at = (
                    datetime.strptime(prepared_text, "%Y-%m-%dT%H:%M")
                    if prepared_text else None
                )

            except ValueError:
                flash("Please enter valid preparation and expiry dates.")
                return render_template(
                    "add_food.html", categories=categories
                )

            if expiry_at <= datetime.now():
                flash("Expiry date must be in the future.")
                return render_template(
                    "add_food.html", categories=categories
                )

            if prepared_at and prepared_at > datetime.now():
                flash("Preparation date cannot be in the future.")
                return render_template(
                    "add_food.html", categories=categories
                )

            if prepared_at and prepared_at >= expiry_at:
                flash("Expiry must be later than preparation time.")
                return render_template(
                    "add_food.html", categories=categories
                )

            cursor.execute("""
                SELECT donor_id
                FROM donor_profiles
                WHERE user_id = %s
            """, (session["user_id"],))

            donor = cursor.fetchone()

            if not donor:
                flash("Donor profile not found.")
                return render_template(
                    "add_food.html", categories=categories
                )

            cursor.execute("""
                INSERT INTO food_listings
                (
                    donor_id, category_id, food_name, description,
                    quantity, unit, prepared_at, expiry_at,
                    pickup_address, city, status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'AVAILABLE')
            """, (
                donor["donor_id"], category_id, food_name,
                description, quantity, unit, prepared_at,
                expiry_at, pickup_address, city
            ))

            connection.commit()

            flash("Food donation added successfully!")
            return redirect(url_for("donor_dashboard"))

    except Exception as e:
        if connection:
            connection.rollback()

        print("Add food error:", e)
        flash("Unable to add food donation. Please try again.")

    finally:
        close_database(connection, cursor)

    return render_template("add_food.html", categories=categories)


# ==========================================
# 11. MY FOOD LISTINGS
# ==========================================

@app.route("/my-listings")
@role_required("DONOR")
def my_listings():

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT donor_id
            FROM donor_profiles
            WHERE user_id = %s
        """, (session["user_id"],))

        donor = cursor.fetchone()

        if not donor:
            flash("Donor profile not found.")
            return redirect(url_for("donor_dashboard"))

        cursor.execute("""
            SELECT
                fl.listing_id,
                fl.food_name,
                fl.description,
                fl.quantity,
                fl.unit,
                fl.expiry_at,
                fl.pickup_address,
                fl.city,
                fl.status,
                fl.created_at,
                fc.category_name
            FROM food_listings fl
            JOIN food_categories fc
                ON fl.category_id = fc.category_id
            WHERE fl.donor_id = %s
            ORDER BY fl.created_at DESC
        """, (donor["donor_id"],))

        listings = cursor.fetchall()

        return render_template(
            "my_listings.html",
            listings=listings
        )

    except Exception as e:
        print("My listings error:", e)
        flash("Unable to load your food listings.")
        return redirect(url_for("donor_dashboard"))

    finally:
        close_database(connection, cursor)



# ==========================================
# FOOD REQUESTS - DONOR
# ==========================================

@app.route("/food-requests")
@role_required("DONOR")
def food_requests():

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        query = """
            SELECT
                fr.request_id,
                fr.requested_quantity,
                fr.request_date,
                fr.status,

                fl.food_name,
                fl.quantity AS listed_quantity,
                fl.unit,
                fl.city,
                fl.expiry_at,

                np.organization_name AS organization_name,
                ngo_user.full_name AS ngo_contact_name,
                ngo_user.email AS ngo_email,
                ngo_user.phone AS ngo_phone

            FROM food_requests fr

            JOIN food_listings fl
                ON fr.listing_id = fl.listing_id

            JOIN donor_profiles dp
                ON fl.donor_id = dp.donor_id

            JOIN ngo_profiles np
                ON fr.ngo_id = np.ngo_id

            JOIN users ngo_user
                ON np.user_id = ngo_user.user_id

            WHERE dp.user_id = %s

            ORDER BY fr.request_date DESC
        """

        cursor.execute(query, (session["user_id"],))
        requests_list = cursor.fetchall()

        return render_template(
            "food_requests.html",
            requests_list=requests_list
        )

    except Exception as e:
        print("Food Requests Error:", e)
        flash("Unable to load food requests.", "error")
        return redirect(url_for("donor_dashboard"))

    finally:
        close_database(connection, cursor)


# ==========================================
# 13. APPROVE FOOD REQUEST
# ==========================================

@app.route("/approve-food-request/<int:request_id>", methods=["POST"])
@role_required("DONOR")
def approve_food_request(request_id):

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT fr.status
            FROM food_requests fr
            JOIN food_listings fl
                ON fr.listing_id = fl.listing_id
            JOIN donor_profiles dp
                ON fl.donor_id = dp.donor_id
            WHERE fr.request_id = %s
              AND dp.user_id = %s
        """, (request_id, session["user_id"]))

        food_request = cursor.fetchone()

        if not food_request:
            flash("Food request not found.")

        elif food_request["status"] != "PENDING":
            flash("This request has already been processed.")

        else:
            cursor.callproc("ApproveFoodRequest", (request_id,))

            for result in cursor.stored_results():
                result.fetchall()

            connection.commit()
            flash("Food request approved successfully.")

    except Exception as e:
        if connection:
            connection.rollback()

        print("Approve Request Error:", e)
        flash("Unable to approve this request.")

    finally:
        close_database(connection, cursor)

    return redirect(url_for("food_requests"))


# ==========================================
# 14. REJECT FOOD REQUEST
# ==========================================

@app.route("/reject-food-request/<int:request_id>", methods=["POST"])
@role_required("DONOR")
def reject_food_request(request_id):

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            UPDATE food_requests fr
            JOIN food_listings fl
                ON fr.listing_id = fl.listing_id
            JOIN donor_profiles dp
                ON fl.donor_id = dp.donor_id
            SET fr.status = 'REJECTED'
            WHERE fr.request_id = %s
              AND dp.user_id = %s
              AND fr.status = 'PENDING'
        """, (request_id, session["user_id"]))

        if cursor.rowcount > 0:
            connection.commit()
            flash("Food request rejected successfully.")
        else:
            connection.rollback()
            flash("Request not found or already processed.")

    except Exception as e:
        if connection:
            connection.rollback()

        print("Reject Request Error:", e)
        flash("Unable to reject this request.")

    finally:
        close_database(connection, cursor)

    return redirect(url_for("food_requests"))


# ==========================================
# 15. NGO - BROWSE AVAILABLE FOOD
# ==========================================

@app.route("/browse-food")
@role_required("NGO")
def browse_food():

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                f.listing_id,
                f.food_name,
                f.description,
                f.quantity,
                f.unit,
                f.expiry_at,
                f.pickup_address,
                f.city,
                c.category_name,
                u.full_name AS donor_name,
                dp.organization_name
            FROM food_listings f
            JOIN food_categories c
                ON f.category_id = c.category_id
            JOIN donor_profiles dp
                ON f.donor_id = dp.donor_id
            JOIN users u
                ON dp.user_id = u.user_id
            WHERE f.status = 'AVAILABLE'
              AND f.expiry_at > NOW()
            ORDER BY f.expiry_at ASC
        """)

        foods = cursor.fetchall()

        return render_template(
            "browse_food.html",
            foods=foods
        )

    except Exception as e:
        print("Browse Food Error:", e)
        flash("Unable to load food listings.")
        return redirect(url_for("ngo_dashboard"))

    finally:
        close_database(connection, cursor)


# ==========================================
# 16. NGO - REQUEST FOOD
# ==========================================

@app.route("/request-food/<int:listing_id>", methods=["POST"])
@role_required("NGO")
def request_food(listing_id):

    connection = None
    cursor = None

    try:
        requested_quantity = float(
            request.form.get("requested_quantity", 0)
        )

        if requested_quantity <= 0:
            flash("Please enter a valid quantity.")
            return redirect(url_for("browse_food"))

        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT ngo_id
            FROM ngo_profiles
            WHERE user_id = %s
        """, (session["user_id"],))

        ngo = cursor.fetchone()

        if not ngo:
            flash("NGO profile not found.")
            return redirect(url_for("browse_food"))

        cursor.execute("""
            SELECT listing_id, quantity, status, expiry_at
            FROM food_listings
            WHERE listing_id = %s
            FOR UPDATE
        """, (listing_id,))

        food = cursor.fetchone()

        if (
            not food
            or food["status"] != "AVAILABLE"
            or food["expiry_at"] <= datetime.now()
        ):
            flash("This food is no longer available.")
            return redirect(url_for("browse_food"))

        if requested_quantity > float(food["quantity"]):
            flash("Requested quantity exceeds available quantity.")
            return redirect(url_for("browse_food"))

        cursor.execute("""
            INSERT INTO food_requests
            (
                listing_id,
                ngo_id,
                requested_quantity,
                request_date,
                status
            )
            VALUES (%s, %s, %s, NOW(), 'PENDING')
        """, (
            listing_id,
            ngo["ngo_id"],
            requested_quantity
        ))

        connection.commit()

        flash(
            "Food request submitted successfully! Waiting for donor approval."
        )

    except Exception as e:
        if connection:
            connection.rollback()

        print("Request Food Error:", e)
        flash("Unable to submit request. Please check the quantity and try again.")

    finally:
        close_database(connection, cursor)

    return redirect(url_for("browse_food"))


# ==========================================
# 17. LOGOUT
# ==========================================

@app.route("/logout")
def logout():
    session.clear()
    flash("You have successfully logged out.")
    return redirect(url_for("login"))


# ==========================================
# 18. RUN APPLICATION
# ==========================================

if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    )
