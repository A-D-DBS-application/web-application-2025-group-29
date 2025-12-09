from datetime import datetime, timezone

from flask import flash, redirect, render_template, request, session, url_for

from ..algorithms import (
    calculate_driver_workload_hours,
    sort_orders_by_priority,
    suggest_best_driver,
)
from ..config import supabase
from .routes import (
    bp,
    build_order_info,
    calculate_driver_availability,
    calculate_statistics_by_task_type,
    convert_orders_for_algorithm,
    generate_available_months,
    get_company_id,
    get_custom_task_times,
    kg_to_tons,
    login_required,
    parse_date_utc,
    validate_user_type,
)


# Voeg een taaktype toe voor het bedrijf
@bp.route("/company/add-task-type", methods=["POST"])
@login_required
def company_add_task_type():
    if not validate_user_type("company"):
        return redirect(url_for("routes.profile"))

    try:
        sb = supabase
        session.get("email")
        company_id = None

        company_id = get_company_id()

        if not company_id:
            flash("Bedrijf niet gevonden.", "error")
            return redirect(url_for("routes.profile"))

        task_type_name = request.form.get("task_type_name", "").strip().lower()
        time_per_1000kg_str = request.form.get("time_per_1000kg", "").strip()

        if not task_type_name:
            flash("Taaktype naam is verplicht.", "error")
            return redirect(url_for("routes.profile"))

        try:
            time_per_1000kg = float(time_per_1000kg_str)
            if time_per_1000kg <= 0:
                raise ValueError("Tijd moet groter zijn dan 0")
        except (ValueError, TypeError):
            flash(
                "Ongeldige tijd per 1000kg. Voer een geldig positief getal in (bijv. 0.1 voor 0.1 uur per 1000kg).",
                "error",
            )
            return redirect(url_for("routes.profile"))

        existing = (
            sb.table("TaskTypes")
            .select("id")
            .eq("company_id", company_id)
            .eq("task_type", task_type_name)
            .limit(1)
            .execute()
        )
        if existing.data:
            flash(f"Taaktype '{task_type_name}' bestaat al voor dit bedrijf.", "error")
            return redirect(url_for("routes.profile"))

        try:
            insert_result = (
                sb.table("TaskTypes")
                .insert(
                    {"company_id": company_id, "task_type": task_type_name, "time_per_1000kg": time_per_1000kg}
                )
                .execute()
            )

            if insert_result.data:
                flash(f"Taaktype '{task_type_name}' succesvol toegevoegd!", "success")
            else:
                flash("Taaktype kon niet worden toegevoegd. Controleer de database instellingen.", "error")
        except Exception as insert_error:
            error_msg = str(insert_error)
            if "row-level security" in error_msg.lower() or "42501" in error_msg:
                flash(
                    f"Fout: Row-Level Security policy blokkeert het toevoegen. Neem contact op met de beheerder om de RLS policies voor de TaskTypes tabel aan te passen. Details: {error_msg}",
                    "error",
                )
            else:
                flash(f"Fout bij het toevoegen van taaktype: {error_msg}", "error")
            raise
    except Exception as e:
        if "row-level security" not in str(e).lower() and "42501" not in str(e):
            flash(f"Fout bij het toevoegen van taaktype: {str(e)}", "error")

    return redirect(url_for("routes.profile"))


# Verwijder een taaktype van het bedrijf
@bp.route("/company/delete-task-type/<int:task_type_id>", methods=["POST"])
@login_required
def company_delete_task_type(task_type_id):
    if not validate_user_type("company"):
        return redirect(url_for("routes.profile"))

    try:
        sb = supabase
        session.get("email")
        company_id = None

        company_id = get_company_id()

        if not company_id:
            flash("Bedrijf niet gevonden.", "error")
            return redirect(url_for("routes.profile"))

        delete_result = (
            sb.table("TaskTypes").delete().eq("id", task_type_id).eq("company_id", company_id).execute()
        )
        if delete_result.data:
            flash("Taaktype succesvol verwijderd!", "success")
        else:
            flash("Taaktype niet gevonden of je hebt geen toegang.", "error")
    except Exception as e:
        flash(f"Fout bij het verwijderen van taaktype: {str(e)}", "error")

    return redirect(url_for("routes.profile"))


# Dashboard voor bedrijven met bestellingen en chauffeurs
@bp.route("/company/dashboard")
@login_required
def company_dashboard():
    if not validate_user_type("company"):
        return redirect(url_for("routes.profile"))

    try:
        company_id = get_company_id()
        if not company_id:
            flash("Bedrijf niet gevonden. Neem contact op met de beheerder.", "error")
            return render_template(
                "company_dashboard.html",
                orders=[],
                drivers=[],
                user_email=session.get("email", ""),
            )

        drivers_result = (
            supabase.table("Drivers")
            .select("id, name, email_address")
            .eq("company_id", company_id)
            .order("name")
            .execute()
        )
        drivers = drivers_result.data if drivers_result.data else []
        custom_task_times = get_custom_task_times(company_id)

        orders_result = (
            supabase.table("Orders")
            .select("*, Address!orders_address_id_fkey(*), TaskTypes!inner(*)")
            .eq("TaskTypes.company_id", company_id)
            .order("created_at", desc=True)
            .limit(100)
            .execute()
        )
        all_orders_raw = orders_result.data if orders_result.data else []

        driver_workload_hours = {}
        if drivers and all_orders_raw:
            orders_for_algo = convert_orders_for_algorithm(all_orders_raw)
            for driver in drivers:
                driver_workload_hours[driver["id"]] = calculate_driver_workload_hours(
                    driver["id"], orders_for_algo, None, custom_task_times
                )

        orders = []
        orders_for_algo = convert_orders_for_algorithm(all_orders_raw) if all_orders_raw else []

        for order in all_orders_raw:
            order_info = build_order_info(order, custom_task_times)

            if not order_info.get("driver_id") and drivers:
                suggestion = suggest_best_driver(
                    drivers, order_info, driver_workload_hours, orders_for_algo, custom_task_times
                )
                if suggestion:
                    order_info["suggested_driver"] = suggestion

                order_deadline_date = None
                if order_info.get("deadline"):
                    try:
                        order_deadline_date = datetime.strptime(order_info["deadline"], "%Y-%m-%d").date()
                    except (ValueError, TypeError):
                        pass

                order_info["driver_availability"] = calculate_driver_availability(
                    drivers, orders_for_algo, order_deadline_date, driver_workload_hours, custom_task_times
                )

            orders.append(order_info)

        orders = sort_orders_by_priority(orders)
        active_orders = [o for o in orders if o.get("status") != "completed"]
        completed_orders = [o for o in orders if o.get("status") == "completed"]

        return render_template(
            "company_dashboard.html",
            active_orders=active_orders,
            completed_orders=completed_orders,
            drivers=drivers,
            user_email=session.get("email", ""),
        )
    except Exception as e:
        flash(f"Fout bij het ophalen van bestellingen: {str(e)}", "error")
        return render_template(
            "company_dashboard.html",
            active_orders=[],
            completed_orders=[],
            drivers=[],
            user_email=session.get("email", ""),
        )


# Statistieken voor het bedrijf (per maand/jaar)
@bp.route("/company/statistics")
@login_required
def company_statistics():
    if not validate_user_type("company"):
        return redirect(url_for("routes.profile"))

    try:
        sb = supabase
        company_email = session.get("email")
        company_id = None
        company_name = None

        company_result = sb.table("Companies").select("id, name").eq("emailaddress", company_email).limit(1).execute()
        if company_result.data:
            company_id = company_result.data[0]["id"]
            company_name = company_result.data[0].get("name", "Bedrijf")

        if not company_id:
            flash("Bedrijf niet gevonden. Neem contact op met de beheerder.", "error")
            return redirect(url_for("routes.home"))

        orders_result = (
            sb.table("Orders")
            .select("*, TaskTypes!inner(*)")
            .eq("TaskTypes.company_id", company_id)
            .eq("status", "completed")
            .execute()
        )
        all_orders = orders_result.data if orders_result.data else []

        selected_month = request.args.get("month")
        if not selected_month:
            now = datetime.now(timezone.utc)
            selected_month = f"{now.year}-{now.month:02d}"

        try:
            selected_year, selected_month_num = map(int, selected_month.split("-"))
            if not (1 <= selected_month_num <= 12):
                raise ValueError("Ongeldige maand")
        except (ValueError, AttributeError):
            now = datetime.now(timezone.utc)
            selected_year = now.year
            selected_month_num = now.month
            selected_month = f"{selected_year}-{selected_month_num:02d}"

        now = datetime.now(timezone.utc)
        current_year_start = datetime(now.year, 1, 1, tzinfo=timezone.utc)

        selected_month_start = datetime(selected_year, selected_month_num, 1, tzinfo=timezone.utc)
        if selected_month_num == 12:
            selected_month_end = datetime(selected_year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            selected_month_end = datetime(selected_year, selected_month_num + 1, 1, tzinfo=timezone.utc)

        orders_selected_month = []
        orders_this_year = []
        for order in all_orders:
            order_date_str = order.get("created_at") or order.get("deadline")
            order_date = parse_date_utc(order_date_str)
            if order_date:
                if selected_month_start <= order_date < selected_month_end:
                    orders_selected_month.append(order)
                if order_date >= current_year_start:
                    orders_this_year.append(order)

        custom_task_types_result = (
            sb.table("TaskTypes").select("id, task_type").eq("company_id", company_id).order("task_type").execute()
        )
        custom_task_types = {}
        if custom_task_types_result.data:
            for tt in custom_task_types_result.data:
                custom_task_types[tt["id"]] = tt["task_type"]

        stats_by_task_selected_month = calculate_statistics_by_task_type(orders_selected_month, custom_task_types)
        year_stats_by_task = calculate_statistics_by_task_type(orders_this_year, custom_task_types)
        total_year_tons = sum(kg_to_tons(order.get("Weight") or order.get("weight")) for order in orders_this_year)

        total_selected_month = sum(d["tons"] for d in stats_by_task_selected_month.values())

        available_months = generate_available_months(all_orders)

        month_names = {
            1: "januari",
            2: "februari",
            3: "maart",
            4: "april",
            5: "mei",
            6: "juni",
            7: "juli",
            8: "augustus",
            9: "september",
            10: "oktober",
            11: "november",
            12: "december",
        }
        selected_month_label = f"{month_names[selected_month_num].capitalize()} {selected_year}"

        current_year = now.year

        return render_template(
            "company_statistics.html",
            company_name=company_name,
            stats_by_task_selected_month=stats_by_task_selected_month,
            stats_by_task_year=year_stats_by_task,
            total_year_tons=total_year_tons,
            total_selected_month=total_selected_month,
            selected_month=selected_month,
            selected_month_label=selected_month_label,
            selected_year=current_year,
            available_months=available_months,
        )
    except Exception as e:
        flash(f"Fout bij het ophalen van statistieken: {str(e)}", "error")
        return redirect(url_for("routes.home"))


# Wijs een chauffeur toe aan een order
@bp.route("/company/assign-driver/<int:order_id>", methods=["POST"])
@login_required
def company_assign_driver(order_id):
    if not validate_user_type("company"):
        return redirect(url_for("routes.profile"))

    driver_id = request.form.get("driver_id")
    if not driver_id:
        flash("Selecteer een chauffeur om toe te wijzen.", "error")
        return redirect(url_for("routes.company_dashboard"))

    try:
        driver_id_int = int(driver_id)
    except (ValueError, TypeError):
        flash("Ongeldige chauffeur geselecteerd.", "error")
        return redirect(url_for("routes.company_dashboard"))

    try:
        sb = supabase
        session.get("email")

        company_id = get_company_id()
        if not company_id:
            flash("Bedrijf niet gevonden. Neem contact op met de beheerder.", "error")
            return redirect(url_for("routes.company_dashboard"))

        driver_result = (
            sb.table("Drivers")
            .select("id")
            .eq("id", driver_id_int)
            .eq("company_id", company_id)
            .limit(1)
            .execute()
        )
        if not driver_result.data or len(driver_result.data) == 0:
            flash("Deze chauffeur hoort niet bij jouw bedrijf.", "error")
            return redirect(url_for("routes.company_dashboard"))

        order_check = (
            sb.table("Orders")
            .select("task_type_id, TaskTypes!inner(company_id)")
            .eq("id", order_id)
            .eq("TaskTypes.company_id", company_id)
            .limit(1)
            .execute()
        )
        if not order_check.data:
            flash("Bestelling niet gevonden of je hebt geen toegang.", "error")
            return redirect(url_for("routes.company_dashboard"))

        update_result = (
            sb.table("Orders")
            .update({"driver_id": driver_id_int, "status": "accepted"})
            .eq("id", order_id)
            .execute()
        )

        if not update_result.data:
            flash("Bestelling niet gevonden of kon niet worden bijgewerkt.", "error")
        else:
            flash("Chauffeur succesvol aan bestelling toegewezen.", "success")

    except Exception as e:
        flash(f"Fout bij het toewijzen van chauffeur: {e}", "error")

    return redirect(url_for("routes.company_dashboard"))

