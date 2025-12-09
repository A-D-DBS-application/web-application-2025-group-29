from datetime import datetime

from flask import flash, g, redirect, render_template, request, session, url_for

from ..config import supabase
from .routes import bp


# Voor elke request: zet current user info in g-context
@bp.before_request
def load_current_user():
    g.current_user_id = session.get("email")
    g.current_user_email = session.get("email")
    g.current_user_type = session.get("user_type", "customer")

    if g.current_user_type == "customer":
        first_name = session.get("first_name", "")
        last_name = session.get("last_name", "")
        g.current_user_display_name = (
            f"{first_name} {last_name}" if first_name and last_name else g.current_user_email
        )
    else:
        g.current_user_display_name = g.current_user_email


# Landing: toon home afhankelijk van user-type
@bp.route("/")
def home():
    user_type = session.get("user_type", "customer")
    user_email = session.get("email")

    if user_type == "company" and user_email:
        try:
            sb = supabase
            company_result = (
                sb.table("Companies")
                .select("id, name")
                .eq("emailaddress", user_email)
                .limit(1)
                .execute()
            )
            company_id = None
            company_name = None

            if company_result.data:
                company_id = company_result.data[0]["id"]
                company_name = company_result.data[0].get("name", "Bedrijf")

            stats = {
                "total_orders": 0,
                "pending_orders": 0,
                "completed_orders": 0,
                "recent_orders": [],
            }

            if company_id:
                orders_result = (
                    sb.table("Orders")
                    .select("id, deadline, created_at, status, TaskTypes!inner(company_id)")
                    .eq("TaskTypes.company_id", company_id)
                    .execute()
                )
                if orders_result.data:
                    stats["total_orders"] = len(orders_result.data)
                    stats["completed_orders"] = sum(
                        1 for o in orders_result.data if o.get("status") == "completed"
                    )
                    stats["pending_orders"] = stats["total_orders"] - stats["completed_orders"]
                    stats["recent_orders"] = sorted(
                        orders_result.data,
                        key=lambda x: x.get("created_at", ""),
                        reverse=True,
                    )[:5]

            return render_template(
                "home.html",
                user_type="company",
                company_name=company_name,
                stats=stats,
            )
        except Exception as e:
            flash(f"Error loading company home: {e}", "error")
            return render_template(
                "home.html",
                user_type="company",
                company_name=None,
                stats={
                    "total_orders": 0,
                    "pending_orders": 0,
                    "completed_orders": 0,
                    "recent_orders": [],
                },
            )

    if user_type == "driver" and user_email:
        return render_template("home.html", user_type="driver")

    return render_template("home.html", user_type=user_type)


# Login zonder wachtwoord op emailadres
@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()

        if not username:
            flash("Gebruikersnaam is verplicht.", "error")
            return render_template("login.html")

        try:
            if supabase is None:
                flash(
                    "Supabase is niet geconfigureerd. Neem contact op met de beheerder.",
                    "error",
                )
                return render_template("login.html")

            sb = supabase

            client_id = None
            company_id = None
            driver_id = None
            first_name = None
            last_name = None
            user_type = None

            result = (
                sb.table("Client")
                .select("id, Name, Lastname")
                .eq("emailaddress", username)
                .limit(1)
                .execute()
            )
            if result.data:
                row = result.data[0]
                client_id = row["id"]
                first_name = row.get("Name")
                last_name = row.get("Lastname")
                user_type = "customer"
            else:
                result = (
                    sb.table("Companies")
                    .select("id, name")
                    .eq("emailaddress", username)
                    .limit(1)
                    .execute()
                )
                if result.data:
                    company_id = result.data[0]["id"]
                    user_type = "company"
                else:
                    result = (
                        sb.table("Drivers")
                        .select("id, name")
                        .eq("email_address", username)
                        .limit(1)
                        .execute()
                    )
                    if result.data:
                        driver_id = result.data[0]["id"]
                        user_type = "driver"

            if not user_type:
                flash("Geen gebruiker gevonden met deze gebruikersnaam.", "error")
                return render_template("login.html")

            session.clear()
            session["email"] = username
            session["user_type"] = user_type

            if client_id is not None:
                session["client_id"] = client_id
            if company_id is not None:
                session["company_id"] = company_id
            if driver_id is not None:
                session["driver_id"] = driver_id
            if first_name:
                session["first_name"] = first_name
            if last_name:
                session["last_name"] = last_name

            session.modified = True

            flash("Succesvol ingelogd.", "success")
            return redirect(url_for("routes.home"))

        except Exception as e:
            flash(f"Inloggen mislukt. Fout: {e}", "error")
            return render_template("login.html")

    return render_template("login.html")


# Signup voor klant/bedrijf/driver
@bp.route("/signup", methods=["GET", "POST"])
def signup():
    user_type = request.args.get("user_type") or request.form.get("user_type") or "customer"
    if user_type not in ["company", "customer", "driver"]:
        user_type = "customer"

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()

        if not username:
            flash("Gebruikersnaam is verplicht.", "error")
            return render_template("signup.html", user_type=user_type)

        if not first_name:
            flash("Voornaam is verplicht.", "error")
            return render_template("signup.html", user_type=user_type)
        if not last_name:
            flash("Achternaam is verplicht.", "error")
            return render_template("signup.html", user_type=user_type)

        try:
            if supabase is None:
                flash(
                    "Supabase is niet geconfigureerd. Neem contact op met de beheerder.",
                    "error",
                )
                return render_template("signup.html", user_type=user_type)

            sb = supabase

            if user_type == "customer":
                existing = (
                    sb.table("Client")
                    .select("id")
                    .eq("emailaddress", username)
                    .limit(1)
                    .execute()
                )
                if existing.data:
                    flash(
                        "Er bestaat al een klant met deze gebruikersnaam. Log in.",
                        "info",
                    )
                    return redirect(url_for("routes.login", user_type=user_type))

                sb.table("Client").insert(
                    {
                        "emailaddress": username,
                        "Name": first_name,
                        "Lastname": last_name,
                        "created_at": datetime.utcnow().isoformat(),
                    }
                ).execute()

            elif user_type == "company":
                existing = (
                    sb.table("Companies")
                    .select("id")
                    .eq("emailaddress", username)
                    .limit(1)
                    .execute()
                )
                if existing.data:
                    flash(
                        "Er bestaat al een bedrijf met deze gebruikersnaam. Log in.",
                        "info",
                    )
                    return redirect(url_for("routes.login", user_type=user_type))

                sb.table("Companies").insert(
                    {
                        "name": username,
                        "emailaddress": username,
                        "created_at": datetime.utcnow().isoformat(),
                    }
                ).execute()

            elif user_type == "driver":
                existing = (
                    sb.table("Drivers")
                    .select("id")
                    .eq("email_address", username)
                    .limit(1)
                    .execute()
                )
                if existing.data:
                    flash(
                        "Er bestaat al een chauffeur met deze gebruikersnaam. Log in.",
                        "info",
                    )
                    return redirect(url_for("routes.login", user_type=user_type))

                sb.table("Drivers").insert(
                    {
                        "email_address": username,
                        "name": f"{first_name} {last_name}".strip(),
                        "created_at": datetime.utcnow().isoformat(),
                    }
                ).execute()

            flash(
                "Account aangemaakt. Je kunt nu inloggen met je gebruikersnaam (zonder wachtwoord).",
                "success",
            )
            return redirect(url_for("routes.login", user_type=user_type))

        except Exception as e:
            flash(f"Registratie mislukt. Fout: {e}", "error")
            return render_template("signup.html", user_type=user_type)

    return render_template("signup.html", user_type=user_type)


# Logout en sessie leegmaken
@bp.route("/logout")
def logout():
    session.clear()
    flash("Uitgelogd.", "success")
    return redirect(url_for("routes.home"))

