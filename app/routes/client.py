from datetime import datetime

from flask import flash, redirect, render_template, request, session, url_for

from ..config import supabase
from .routes import (
    bp,
    build_order_info_for_edit,
    format_address_data,
    get_addresses_for_client,
    get_client_id,
    get_company_id,
    get_companies_list,
    get_previous_orders_for_customer,
    get_task_type_name,
    is_order_overdue,
    login_required,
    validate_user_type,
)


@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user_type = session.get("user_type", "customer")
    user_ctx = {"emailaddress": session.get("email", ""), "user_type": user_type}
    addresses = []
    custom_task_types = []
    sb = supabase

    if user_type == "driver":
        try:
            driver_result = (
                sb.table("Drivers")
                .select("id, name, company_id")
                .eq("email_address", session.get("email"))
                .limit(1)
                .execute()
            )
            if driver_result.data:
                driver_data = driver_result.data[0]
                if driver_data.get("name"):
                    user_ctx["display_name"] = driver_data["name"]
                company_id = driver_data.get("company_id")
                if company_id:
                    company_result = (
                        sb.table("Companies").select("name").eq("id", company_id).limit(1).execute()
                    )
                    if company_result.data:
                        user_ctx["company_name"] = company_result.data[0].get("name", "")
        except Exception:
            pass

    elif user_type == "customer":
        first_name = session.get("first_name", "")
        last_name = session.get("last_name", "")
        if not (first_name or last_name):
            try:
                client_id = session.get("client_id") or get_client_id()
                if client_id:
                    client_result = (
                        sb.table("Client").select("Name, Lastname").eq("id", client_id).limit(1).execute()
                    )
                    if client_result.data:
                        client_data = client_result.data[0]
                        first_name = client_data.get("Name", "")
                        last_name = client_data.get("Lastname", "")
                        if first_name or last_name:
                            session["first_name"] = first_name
                            session["last_name"] = last_name
            except Exception:
                pass

        if first_name or last_name:
            user_ctx["first_name"] = first_name
            user_ctx["last_name"] = last_name
            user_ctx["display_name"] = f"{first_name} {last_name}".strip()

        try:
            client_id = get_client_id()
            if client_id:
                addresses_result = (
                    sb.table("Address")
                    .select("*")
                    .eq("client_id", client_id)
                    .order("created_at", desc=False)
                    .execute()
                )
                addresses = addresses_result.data if addresses_result.data else []
        except Exception as e:
            flash(f"Kon adressen niet ophalen: {e}", "error")

    elif user_type == "company":
        try:
            company_id = get_company_id()
            if company_id:
                task_types_result = (
                    sb.table("TaskTypes")
                    .select("*")
                    .eq("company_id", company_id)
                    .order("task_type")
                    .execute()
                )
                custom_task_types = task_types_result.data if task_types_result.data else []
        except Exception as e:
            flash(f"Kon taaktypes niet ophalen: {e}", "error")

    return render_template(
        "profile.html", user=user_ctx, addresses=addresses, custom_task_types=custom_task_types
    )


@bp.route("/profile/add-address", methods=["POST"])
@login_required
def add_address():
    if not validate_user_type("customer"):
        return redirect(url_for("routes.profile"))

    try:
        sb = supabase
        client_id = get_client_id()

        if not client_id:
            flash("Klant niet gevonden.", "error")
            return redirect(url_for("routes.profile"))

        house_number_raw = request.form.get("house_number")
        try:
            house_number_val = int(house_number_raw) if house_number_raw is not None else None
        except ValueError:
            house_number_val = None

        address_data = {
            "client_id": client_id,
            "street_name": request.form.get("street_name"),
            "house_number": house_number_val,
            "city": request.form.get("city"),
            "phone_number": request.form.get("phone_number"),
        }

        address_result = sb.table("Address").insert(address_data).execute()

        if address_result.data:
            flash("Adres succesvol toegevoegd!", "success")
        else:
            flash("Adres kon niet worden toegevoegd.", "error")
    except Exception as e:
        flash(f"Fout bij het toevoegen van adres: {str(e)}", "error")

    return redirect(url_for("routes.profile"))


@bp.route("/profile/delete-address/<int:address_id>", methods=["POST"])
@login_required
def delete_address(address_id):
    if not validate_user_type("customer"):
        return redirect(url_for("routes.profile"))

    try:
        sb = supabase
        client_id = get_client_id()

        if not client_id:
            flash("Klant niet gevonden.", "error")
            return redirect(url_for("routes.profile"))

        address_result = (
            sb.table("Address")
            .select("client_id")
            .eq("id", address_id)
            .eq("client_id", client_id)
            .limit(1)
            .execute()
        )
        if not address_result.data or len(address_result.data) == 0:
            flash("Adres niet gevonden of je hebt geen toegang tot dit adres.", "error")
            return redirect(url_for("routes.profile"))

        orders_result = sb.table("Orders").select("id").eq("address_id", address_id).limit(1).execute()
        if orders_result.data:
            flash(
                "Dit adres kan niet worden verwijderd omdat het gebruikt wordt in een bestelling.",
                "error",
            )
            return redirect(url_for("routes.profile"))

        delete_result = (
            sb.table("Address").delete().eq("id", address_id).eq("client_id", client_id).execute()
        )

        if delete_result.data:
            flash("Adres succesvol verwijderd!", "success")
        else:
            flash("Adres kon niet worden verwijderd.", "error")
    except Exception as e:
        flash(f"Fout bij het verwijderen van adres: {str(e)}", "error")

    return redirect(url_for("routes.profile"))


@bp.route("/customer/orders")
@login_required
def customer_orders():
    if not validate_user_type("customer"):
        return redirect(url_for("routes.profile"))

    try:
        client_id = get_client_id()
        if not client_id:
            return render_template(
                "customer_orders.html",
                active_orders=[],
                completed_orders=[],
                user_email=session.get("email", ""),
            )

        addresses_result = supabase.table("Address").select("id").eq("client_id", client_id).execute()
        address_ids = [addr["id"] for addr in addresses_result.data] if addresses_result.data else []

        if not address_ids:
            return render_template(
                "customer_orders.html",
                active_orders=[],
                completed_orders=[],
                user_email=session.get("email", ""),
            )

        orders_result = (
            supabase.table("Orders")
            .select("*, Address!orders_address_id_fkey(*), TaskTypes(*)")
            .in_("address_id", address_ids)
            .order("created_at", desc=True)
            .limit(100)
            .execute()
        )

        orders = []
        if orders_result and orders_result.data:
            for order in orders_result.data:
                order_info = {
                    "id": order.get("id"),
                    "deadline": order.get("deadline"),
                    "task_type": get_task_type_name(order.get("task_type_id"), order.get("TaskTypes")),
                    "product_type": order.get("product_type"),
                    "created_at": order.get("created_at"),
                    "address": format_address_data(order.get("Address")),
                    "company": None,
                    "driver_id": order.get("driver_id"),
                    "driver_name": None,
                    "status": order.get("status"),
                    "is_overdue": is_order_overdue(order.get("deadline"), order.get("status")),
                }

                task_type_id = order.get("task_type_id")
                if task_type_id and order.get("TaskTypes"):
                    company_id_from_task = order["TaskTypes"].get("company_id")
                    if company_id_from_task:
                        try:
                            company_result = (
                                supabase.table("Companies")
                                .select("name, id")
                                .eq("id", company_id_from_task)
                                .limit(1)
                                .execute()
                            )
                            if company_result.data:
                                company = company_result.data[0]
                                order_info["company"] = {"name": company.get("name"), "id": company.get("id")}
                        except Exception:
                            pass

                driver_id = order.get("driver_id")
                if driver_id:
                    try:
                        driver_result = (
                            supabase.table("Drivers")
                            .select("name")
                            .eq("id", driver_id)
                            .limit(1)
                            .execute()
                        )
                        if driver_result.data:
                            order_info["driver_name"] = driver_result.data[0].get("name", "Onbekend")
                    except Exception:
                        pass

                orders.append(order_info)

        active_orders = [o for o in orders if o.get("status") != "completed"]
        completed_orders = [o for o in orders if o.get("status") == "completed"]

        return render_template(
            "customer_orders.html",
            active_orders=active_orders,
            completed_orders=completed_orders,
            user_email=session.get("email", ""),
        )
    except Exception as e:
        flash(f"Fout bij het ophalen van bestellingen: {str(e)}", "error")
        return render_template(
            "customer_orders.html",
            active_orders=[],
            completed_orders=[],
            user_email=session.get("email", ""),
        )


@bp.route("/customer/cancel-order/<int:order_id>", methods=["POST"])
@login_required
def cancel_order(order_id):
    if not validate_user_type("customer"):
        return redirect(url_for("routes.profile"))

    try:
        sb = supabase
        client_id = get_client_id()

        if not client_id:
            flash("Klant niet gevonden.", "error")
            return redirect(url_for("routes.customer_orders"))

        order_result = (
            sb.table("Orders")
            .select(
                "id, driver_id, status, address_id, Address!orders_address_id_fkey!inner(client_id)"
            )
            .eq("id", order_id)
            .eq("Address.client_id", client_id)
            .limit(1)
            .execute()
        )

        if not order_result.data or len(order_result.data) == 0:
            flash("Bestelling niet gevonden of je hebt geen toegang tot deze bestelling.", "error")
            return redirect(url_for("routes.customer_orders"))

        order = order_result.data[0]

        if order.get("driver_id"):
            flash(
                "Deze bestelling kan niet worden geannuleerd omdat deze al is toegewezen aan een chauffeur.",
                "error",
            )
            return redirect(url_for("routes.customer_orders"))

        if order.get("status") == "completed":
            flash("Deze bestelling kan niet worden geannuleerd omdat deze al is voltooid.", "error")
            return redirect(url_for("routes.customer_orders"))

        delete_result = sb.table("Orders").delete().eq("id", order_id).execute()

        if delete_result.data:
            flash("Bestelling succesvol geannuleerd.", "success")
        else:
            flash("Bestelling kon niet worden geannuleerd.", "error")

    except Exception as e:
        flash(f"Fout bij het annuleren van bestelling: {str(e)}", "error")

    return redirect(url_for("routes.customer_orders"))


@bp.route("/customer/orders/<int:order_id>/edit", methods=["GET", "POST"])
@login_required
def edit_order(order_id):
    if not validate_user_type("customer"):
        return redirect(url_for("routes.profile"))

    sb = supabase

    try:
        client_id = get_client_id()
        if not client_id:
            flash("Klant niet gevonden.", "error")
            return redirect(url_for("routes.customer_orders"))

        order_result = (
            sb.table("Orders")
            .select("*, Address!orders_address_id_fkey!inner(*), TaskTypes(*)")
            .eq("id", order_id)
            .eq("Address.client_id", client_id)
            .limit(1)
            .execute()
        )
        if not order_result.data:
            flash("Bestelling niet gevonden of je hebt geen toegang tot deze bestelling.", "error")
            return redirect(url_for("routes.customer_orders"))

        order_data = order_result.data[0]
        driver_id = order_data.get("driver_id")
        if driver_id:
            driver_name = "een chauffeur"
            try:
                driver_result = (
                    sb.table("Drivers").select("name").eq("id", driver_id).limit(1).execute()
                )
                if driver_result.data:
                    driver_name = driver_result.data[0].get("name") or driver_name
            except Exception:
                pass
            flash(
                f"Deze bestelling kan niet meer bewerkt worden omdat deze is toegewezen aan {driver_name}.",
                "error",
            )
            return redirect(url_for("routes.customer_orders"))

        companies = get_companies_list()
        addresses = get_addresses_for_client(client_id)
        order_info = build_order_info_for_edit(order_data)

        template_vars = {"order": order_info, "companies": companies, "addresses": addresses}

        if request.method == "POST":
            try:
                address_id_str = request.form.get("address_id")

                if address_id_str:
                    try:
                        selected_address_id = int(address_id_str)
                        address_check = (
                            sb.table("Address")
                            .select("id")
                            .eq("id", selected_address_id)
                            .eq("client_id", client_id)
                            .limit(1)
                            .execute()
                        )
                        if not address_check.data:
                            flash("Ongeldig adres geselecteerd.", "error")
                            return render_template("edit_order.html", **template_vars)
                    except (ValueError, TypeError):
                        flash("Ongeldig adres geselecteerd.", "error")
                        return render_template("edit_order.html", **template_vars)
                else:
                    flash("Selecteer een adres.", "error")
                    return render_template("edit_order.html", **template_vars)

                company_id = request.form.get("company_id")
                if not company_id:
                    flash("Bedrijf is verplicht. Selecteer een bedrijf.", "error")
                    return render_template("edit_order.html", **template_vars)

                try:
                    company_id = int(company_id)
                except (ValueError, TypeError):
                    flash("Ongeldig bedrijf geselecteerd.", "error")
                    return render_template("edit_order.html", **template_vars)

                task_type_value = request.form.get("task_type")
                task_type_id = None
                if task_type_value:
                    try:
                        task_type_id = int(task_type_value)
                    except (ValueError, TypeError):
                        pass

                weight_str = request.form.get("weight", "").strip()
                weight = None
                if weight_str:
                    try:
                        weight = float(weight_str)
                    except (ValueError, TypeError):
                        flash("Ongeldig gewicht. Voer een geldig getal in.", "error")
                        return render_template("edit_order.html", **template_vars)

                order_update_data = {
                    "deadline": request.form.get("deadline"),
                    "task_type_id": task_type_id if task_type_id else None,
                    "product_type": request.form.get("product_type"),
                    "Weight": weight,
                    "address_id": selected_address_id,
                }

                order_update_result = sb.table("Orders").update(order_update_data).eq("id", order_id).execute()

                if order_update_result.data:
                    flash("Bestelling bijgewerkt!", "success")
                    return redirect(url_for("routes.customer_orders"))
                else:
                    flash("Bestelling kon niet worden bijgewerkt.", "error")
            except Exception as e:
                flash(f"Fout bij het bijwerken van bestelling: {str(e)}", "error")
                return render_template("edit_order.html", **template_vars)

        return render_template("edit_order.html", **template_vars)

    except Exception as e:
        flash(f"Fout bij het ophalen van bestelling: {str(e)}", "error")
        return redirect(url_for("routes.customer_orders"))


@bp.route("/order", methods=["GET", "POST"])
@login_required
def order():
    user_type = session.get("user_type", "customer")
    if user_type == "company":
        flash(
            "Bedrijven kunnen geen bestellingen plaatsen. Gebruik het dashboard om bestellingen te bekijken.",
            "error",
        )
        return redirect(url_for("routes.company_dashboard"))

    sb = supabase
    client_id = get_client_id()
    companies = get_companies_list()
    addresses = get_addresses_for_client(client_id)
    previous_orders = get_previous_orders_for_customer(client_id)
    previous_orders.sort(key=lambda x: x.get("created_at", ""), reverse=True)

    if request.method == "POST":
        try:
            address_id_str = request.form.get("address_id")

            if address_id_str:
                try:
                    address_id = int(address_id_str)
                    client_id = get_client_id()

                    if client_id:
                        address_check = (
                            sb.table("Address")
                            .select("id")
                            .eq("id", address_id)
                            .eq("client_id", client_id)
                            .limit(1)
                            .execute()
                        )
                        if not address_check.data or len(address_check.data) == 0:
                            flash("Ongeldig adres geselecteerd.", "error")
                            return render_template(
                                "order.html",
                                companies=companies,
                                addresses=addresses,
                                previous_orders=previous_orders,
                            )
                except (ValueError, TypeError):
                    flash("Ongeldig adres geselecteerd.", "error")
                    return render_template(
                        "order.html", companies=companies, addresses=addresses, previous_orders=previous_orders
                    )
            else:
                flash("Selecteer een adres of voeg eerst een adres toe in je profiel.", "error")
                return render_template(
                    "order.html", companies=companies, addresses=addresses, previous_orders=previous_orders
                )

            company_id = request.form.get("company_id")
            if not company_id:
                flash("Bedrijf is verplicht. Selecteer een bedrijf.", "error")
                return render_template(
                    "order.html", companies=companies, addresses=addresses, previous_orders=previous_orders
                )

            try:
                company_id = int(company_id)
            except (ValueError, TypeError):
                flash("Ongeldig bedrijf geselecteerd.", "error")
                return render_template(
                    "order.html", companies=companies, addresses=addresses, previous_orders=previous_orders
                )

            weight = None
            weight_str = request.form.get("weight", "").strip()
            if weight_str:
                try:
                    weight = float(weight_str)
                except (ValueError, TypeError):
                    flash("Ongeldig gewicht. Voer een geldig getal in.", "error")
                    return render_template(
                        "order.html", companies=companies, addresses=addresses, previous_orders=previous_orders
                    )

            if weight is None or weight <= 0:
                flash("Gewicht is verplicht en moet groter zijn dan 0.", "error")
                return render_template(
                    "order.html", companies=companies, addresses=addresses, previous_orders=previous_orders
                )

            client_id = session.get("client_id")
            if not client_id:
                try:
                    customer_email = session.get("email")
                    client_result = (
                        sb.table("Client")
                        .select("id, Name, Lastname")
                        .eq("emailaddress", customer_email)
                        .limit(1)
                        .execute()
                    )
                    if client_result.data:
                        client_id = client_result.data[0]["id"]
                        session["client_id"] = client_id
                        first_name = client_result.data[0].get("Name", "")
                        last_name = client_result.data[0].get("Lastname", "")
                        if first_name:
                            session["first_name"] = first_name
                        if last_name:
                            session["last_name"] = last_name
                    else:
                        new_client = (
                            sb.table("Client")
                            .insert({"emailaddress": customer_email, "created_at": datetime.utcnow().isoformat()})
                            .execute()
                        )
                        if new_client.data:
                            client_id = new_client.data[0]["id"]
                            session["client_id"] = client_id
                except Exception:
                    pass

            task_type_value = request.form.get("task_type")
            task_type_id = None
            if task_type_value:
                try:
                    task_type_id = int(task_type_value)
                except (ValueError, TypeError):
                    pass

            order_data = {
                "deadline": request.form.get("deadline"),
                "task_type_id": task_type_id if task_type_id else None,
                "product_type": request.form.get("product_type"),
                "address_id": address_id,
                "status": "pending",
                "Weight": weight,
            }

            order_result = sb.table("Orders").insert(order_data).execute()

            if order_result.data:
                flash("Bestelling geplaatst!", "success")
                return redirect(url_for("routes.home"))
            else:
                flash("Bestelling kon niet worden geplaatst.", "error")
        except Exception as e:
            flash(f"Fout bij het plaatsen van bestelling: {str(e)}", "error")
            return render_template("order.html", companies=companies, addresses=addresses, previous_orders=previous_orders)

    return render_template("order.html", companies=companies, addresses=addresses, previous_orders=previous_orders)


@bp.route("/api/company/<int:company_id>/task-types", methods=["GET"])
def get_company_task_types(company_id):
    try:
        sb = supabase
        task_types_result = (
            sb.table("TaskTypes").select("id, task_type").eq("company_id", company_id).order("task_type").execute()
        )

        task_types = []
        if task_types_result.data:
            task_types = [{"id": tt["id"], "name": tt["task_type"]} for tt in task_types_result.data]

        from flask import jsonify

        return jsonify({"task_types": task_types, "has_task_types": len(task_types) > 0})
    except Exception as e:
        from flask import jsonify

        return jsonify({"error": str(e)}), 500

