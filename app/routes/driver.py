from flask import flash, redirect, render_template, request, session, url_for

from ..config import supabase
from .routes import (
    bp,
    build_order_info,
    calculate_order_time_hours,
    get_custom_task_times,
    login_required,
    validate_user_type,
)


@bp.route("/driver/select-company", methods=["GET", "POST"])
@login_required
def driver_select_company():
    if not validate_user_type("driver"):
        return redirect(url_for("routes.profile"))

    user_email = session.get("email")

    if request.method == "POST":
        company_id = request.form.get("company_id")
        if not company_id:
            flash("Selecteer een bedrijf.", "error")
            return redirect(url_for("routes.driver_select_company"))

        try:
            sb = supabase
            driver_result = (
                sb.table("Drivers").select("id").eq("email_address", user_email).limit(1).execute()
            )

            if driver_result.data:
                driver_id = driver_result.data[0]["id"]
                sb.table("Drivers").update({"company_id": int(company_id)}).eq("id", driver_id).execute()
            else:
                sb.table("Drivers").insert(
                    {
                        "email_address": user_email,
                        "company_id": int(company_id),
                        "name": user_email.split("@")[0],
                    }
                ).execute()

            flash("Bedrijf succesvol geselecteerd!", "success")
            return redirect(url_for("routes.home"))
        except Exception as e:
            flash(f"Fout bij het selecteren van bedrijf: {str(e)}", "error")

    try:
        sb = supabase
        companies_result = sb.table("Companies").select("id, name").order("name").execute()
        companies = companies_result.data if companies_result.data else []

        driver_result = sb.table("Drivers").select("company_id").eq("email_address", user_email).limit(1).execute()
        if driver_result.data and driver_result.data[0].get("company_id"):
            return redirect(url_for("routes.home"))

        return render_template("driver_select_company.html", companies=companies)
    except Exception as e:
        flash(f"Fout bij het ophalen van bedrijven: {str(e)}", "error")
        return render_template("driver_select_company.html", companies=[])


@bp.route("/driver/dashboard")
@login_required
def driver_dashboard():
    if not validate_user_type("driver"):
        return redirect(url_for("routes.profile"))

    try:
        user_email = session.get("email")

        driver_result = (
            supabase.table("Drivers").select("id, company_id").eq("email_address", user_email).limit(1).execute()
        )
        if not driver_result.data:
            return redirect(url_for("routes.driver_select_company"))

        driver_id = driver_result.data[0]["id"]
        company_id = driver_result.data[0].get("company_id")

        if not company_id:
            return redirect(url_for("routes.driver_select_company"))

        custom_task_times = get_custom_task_times(company_id)

        orders_result = (
            supabase.table("Orders")
            .select("*, Address!orders_address_id_fkey(*), TaskTypes(*)")
            .eq("driver_id", driver_id)
            .in_("status", ["accepted", "completed"])
            .order("deadline", desc=False)
            .limit(100)
            .execute()
        )

        orders = []
        if orders_result.data:
            for order in orders_result.data:
                order_info = build_order_info(order, custom_task_times)
                order_info["weight"] = order.get("Weight") or order.get("weight")

                order_for_time = {
                    "task_type_id": order.get("task_type_id"),
                    "Weight": order_info["weight"],
                    "weight": order_info["weight"],
                }
                if order.get("task_type_id") and order.get("task_type_id") in custom_task_times:
                    order_for_time["_custom_time_per_1000kg"] = custom_task_times[order.get("task_type_id")]

                order_info["work_time_hours"] = max(
                    0.0, calculate_order_time_hours(order_for_time, custom_task_times) - 0.75
                )

                if order.get("Companies"):
                    order_info["company"] = {"name": order["Companies"].get("name")}

                orders.append(order_info)

        active_orders = [o for o in orders if o.get("status") != "completed"]
        completed_orders = [o for o in orders if o.get("status") == "completed"]

        return render_template(
            "driver_dashboard.html",
            active_orders=active_orders,
            completed_orders=completed_orders,
            user_email=user_email,
        )
    except Exception as e:
        flash(f"Fout bij het ophalen van ritten: {str(e)}", "error")
        return render_template(
            "driver_dashboard.html",
            active_orders=[],
            completed_orders=[],
            user_email=session.get("email", ""),
        )


@bp.route("/driver/complete-order/<int:order_id>", methods=["POST"])
@login_required
def driver_complete_order(order_id):
    if not validate_user_type("driver"):
        return redirect(url_for("routes.profile"))

    try:
        sb = supabase
        driver_email = session.get("email")

        driver_result = sb.table("Drivers").select("id").eq("email_address", driver_email).limit(1).execute()
        if not driver_result.data or len(driver_result.data) == 0:
            flash("Chauffeur niet gevonden.", "error")
            return redirect(url_for("routes.driver_dashboard"))

        driver_id = driver_result.data[0]["id"]

        order_result = (
            sb.table("Orders").select("id, driver_id").eq("id", order_id).eq("driver_id", driver_id).limit(1).execute()
        )
        if not order_result.data or len(order_result.data) == 0:
            flash("Bestelling niet gevonden of niet aan jou toegewezen.", "error")
            return redirect(url_for("routes.driver_dashboard"))

        update_result = (
            sb.table("Orders").update({"status": "completed"}).eq("id", order_id).eq("driver_id", driver_id).execute()
        )

        if update_result.data:
            flash("Taak gemarkeerd als uitgevoerd!", "success")
        else:
            flash("Taak kon niet worden bijgewerkt.", "error")

    except Exception as e:
        flash(f"Fout bij het markeren van taak: {e}", "error")

    return redirect(url_for("routes.driver_dashboard"))

