from datetime import datetime, timezone

from flask import Blueprint, flash, redirect, session, url_for

from ..algorithms import (
    calculate_driver_workload_hours,
    calculate_order_time_hours,
    filter_duplicate_orders,
)
from ..config import supabase

bp = Blueprint("routes", __name__)


def login_required(view_func):
    def wrapped(*args, **kwargs):
        if "email" not in session or "user_type" not in session:
            flash("Je moet ingelogd zijn.", "error")
            return redirect(url_for("routes.login"))
        return view_func(*args, **kwargs)

    wrapped.__name__ = view_func.__name__
    return wrapped


def get_client_id():
    client_id = session.get("client_id")
    if not client_id:
        customer_email = session.get("email")
        if customer_email:
            try:
                client_result = (
                    supabase.table("Client")
                    .select("id")
                    .eq("emailaddress", customer_email)
                    .limit(1)
                    .execute()
                )
                if client_result.data:
                    client_id = client_result.data[0]["id"]
                    session["client_id"] = client_id
            except Exception:
                pass
    return client_id


def get_company_id():
    company_id = session.get("company_id")
    if not company_id:
        company_email = session.get("email")
        if company_email:
            try:
                company_result = (
                    supabase.table("Companies")
                    .select("id")
                    .eq("emailaddress", company_email)
                    .limit(1)
                    .execute()
                )
                if company_result.data:
                    company_id = company_result.data[0]["id"]
                    session["company_id"] = company_id
            except Exception:
                pass
    return company_id


def get_task_type_name(task_type_id, task_types_data=None):
    if task_types_data:
        return task_types_data.get("task_type")
    if task_type_id:
        try:
            result = (
                supabase.table("TaskTypes")
                .select("task_type")
                .eq("id", task_type_id)
                .limit(1)
                .execute()
            )
            if result.data:
                return result.data[0].get("task_type")
        except Exception:
            pass
    return None


def get_customer_info_from_address(address_id):
    if not address_id:
        return None, None
    try:
        address_result = (
            supabase.table("Address")
            .select("client_id")
            .eq("id", address_id)
            .limit(1)
            .execute()
        )
        if address_result.data:
            client_id = address_result.data[0].get("client_id")
            if client_id:
                client_result = (
                    supabase.table("Client")
                    .select("Name, Lastname")
                    .eq("id", client_id)
                    .limit(1)
                    .execute()
                )
                if client_result.data:
                    return (
                        client_result.data[0].get("Name", ""),
                        client_result.data[0].get("Lastname", ""),
                    )
    except Exception:
        pass
    return None, None


def format_address_data(address_data):
    if not address_data:
        return None
    return {
        "street_name": address_data.get("street_name"),
        "house_number": address_data.get("house_number"),
        "city": address_data.get("city"),
        "phone_number": address_data.get("phone_number"),
    }


def convert_orders_for_algorithm(orders_raw):
    return [
        {
            "driver_id": o.get("driver_id"),
            "status": o.get("status"),
            "deadline": o.get("deadline"),
            "task_type_id": o.get("task_type_id"),
            "task_type": o.get("task_type"),
            "Weight": o.get("Weight") or o.get("weight"),
            "weight": o.get("Weight") or o.get("weight"),
        }
        for o in orders_raw
    ]


def calculate_driver_availability(
    drivers, orders_for_algo, order_deadline, driver_workload_hours, custom_task_times
):
    driver_availability = []
    for driver in drivers:
        driver_id = driver["id"]
        if order_deadline:
            hours_on_deadline = calculate_driver_workload_hours(
                driver_id, orders_for_algo, order_deadline, custom_task_times
            )
            available_hours = 12.0 - hours_on_deadline
        else:
            total_hours = driver_workload_hours.get(driver_id, 0.0)
            available_hours = 12.0 - (total_hours % 12.0) if total_hours > 0 else 12.0

        driver_availability.append(
            {
                "driver_id": driver_id,
                "driver_name": driver.get("name", "Onbekend"),
                "available_hours": max(0.0, available_hours),
            }
        )
    return driver_availability


def build_order_info(order, custom_task_times=None):
    task_type_id = order.get("task_type_id")
    task_type_name = get_task_type_name(task_type_id, order.get("TaskTypes"))

    order_info = {
        "id": order.get("id"),
        "deadline": order.get("deadline"),
        "task_type": task_type_name,
        "task_type_id": task_type_id,
        "product_type": order.get("product_type"),
        "created_at": order.get("created_at"),
        "address": format_address_data(order.get("Address")),
        "driver_id": order.get("driver_id"),
        "status": order.get("status"),
        "Weight": order.get("Weight") or order.get("weight"),
    }

    address_id = order.get("address_id")
    customer_name, customer_lastname = get_customer_info_from_address(address_id)
    order_info["customer_name"] = customer_name
    order_info["customer_lastname"] = customer_lastname

    if custom_task_times and task_type_id:
        order_for_time = order_info.copy()
        if task_type_id in custom_task_times:
            order_for_time["_custom_time_per_1000kg"] = custom_task_times[task_type_id]
        order_info["estimated_time_hours"] = calculate_order_time_hours(
            order_for_time,
            custom_task_times if task_type_id in custom_task_times else None,
        )

    order_info["is_overdue"] = is_order_overdue(order.get("deadline"), order.get("status"))

    return order_info


def validate_user_type(required_type):
    user_type = session.get("user_type", "customer")
    if user_type != required_type:
        flash("Je hebt geen toegang tot deze pagina.", "error")
        return False
    return True


def get_custom_task_times(company_id):
    try:
        result = (
            supabase.table("TaskTypes")
            .select("id, task_type, time_per_1000kg")
            .eq("company_id", company_id)
            .execute()
        )
        if result.data:
            return {tt["id"]: float(tt.get("time_per_1000kg", 1.0)) for tt in result.data}
    except Exception:
        pass
    return {}


def get_previous_orders_for_customer(client_id):
    previous_orders = []
    if not client_id:
        return previous_orders
    try:
        addresses_result = (
            supabase.table("Address").select("id").eq("client_id", client_id).execute()
        )
        address_ids = [addr["id"] for addr in addresses_result.data] if addresses_result.data else []
        if not address_ids:
            return previous_orders
        orders_result = (
            supabase.table("Orders")
            .select("*, Address!orders_address_id_fkey(*), TaskTypes(*)")
            .in_("address_id", address_ids)
            .eq("status", "completed")
            .order("created_at", desc=True)
            .limit(10)
            .execute()
        )
        if orders_result and orders_result.data:
            for order in orders_result.data:
                task_type_name = None
                task_type_id = order.get("task_type_id")
                company_id_from_task = None
                if order.get("TaskTypes"):
                    task_type_name = order["TaskTypes"].get("task_type")
                    company_id_from_task = order["TaskTypes"].get("company_id")
                elif task_type_id:
                    try:
                        task_type_result = (
                            supabase.table("TaskTypes")
                            .select("task_type, company_id")
                            .eq("id", task_type_id)
                            .limit(1)
                            .execute()
                        )
                        if task_type_result.data:
                            task_type_name = task_type_result.data[0].get("task_type")
                            company_id_from_task = task_type_result.data[0].get(
                                "company_id"
                            )
                    except Exception:
                        pass
                order_info = {
                    "id": order.get("id"),
                    "task_type": task_type_name,
                    "task_type_id": task_type_id,
                    "product_type": order.get("product_type"),
                    "weight": order.get("Weight") or order.get("weight"),
                    "company_id": company_id_from_task,
                    "company_name": None,
                    "address_id": order.get("address_id"),
                    "address": None,
                    "deadline": order.get("deadline"),
                    "created_at": order.get("created_at"),
                }
                if company_id_from_task:
                    try:
                        company_result = (
                            supabase.table("Companies")
                            .select("name")
                            .eq("id", company_id_from_task)
                            .limit(1)
                            .execute()
                        )
                        if company_result.data:
                            order_info["company_name"] = company_result.data[0].get("name")
                    except Exception:
                        pass
                if order.get("Address"):
                    addr = order["Address"]
                    order_info["address"] = {
                        "id": addr.get("id"),
                        "street_name": addr.get("street_name"),
                        "house_number": addr.get("house_number"),
                        "city": addr.get("city"),
                        "phone_number": addr.get("phone_number"),
                    }
                previous_orders.append(order_info)
    except Exception:
        pass
    return filter_duplicate_orders(previous_orders)


def get_companies_list():
    companies = []
    try:
        companies_result = (
            supabase.table("Companies").select("id, name, emailaddress").order("name").execute()
        )
        if companies_result.data:
            companies = [{"id": c["id"], "name": c["name"]} for c in companies_result.data]
    except Exception:
        pass
    return companies


def get_addresses_for_client(client_id):
    addresses = []
    if not client_id:
        return addresses
    try:
        addresses_result = (
            supabase.table("Address")
            .select("*")
            .eq("client_id", client_id)
            .order("created_at", desc=False)
            .execute()
        )
        if addresses_result.data:
            addresses = addresses_result.data
    except Exception:
        pass
    return addresses


def build_order_info_for_edit(order_data):
    task_type_name = None
    task_type_id = order_data.get("task_type_id")
    if order_data.get("TaskTypes"):
        task_type_name = order_data["TaskTypes"].get("task_type")
    elif task_type_id:
        try:
            task_type_result = (
                supabase.table("TaskTypes")
                .select("task_type")
                .eq("id", task_type_id)
                .limit(1)
                .execute()
            )
            if task_type_result.data:
                task_type_name = task_type_result.data[0].get("task_type")
        except Exception:
            pass
    order_info = {
        "id": order_data.get("id"),
        "deadline": order_data.get("deadline"),
        "task_type": task_type_name,
        "task_type_id": task_type_id,
        "product_type": order_data.get("product_type"),
        "weight": order_data.get("Weight") or order_data.get("weight"),
        "created_at": order_data.get("created_at"),
        "address": None,
        "company": None,
        "address_id": order_data.get("address_id"),
    }
    if order_data.get("Address"):
        addr = order_data["Address"]
        order_info["address"] = {
            "street_name": addr.get("street_name"),
            "house_number": addr.get("house_number"),
            "city": addr.get("city"),
            "phone_number": addr.get("phone_number"),
            "id": addr.get("id"),
        }
    if task_type_id and order_data.get("TaskTypes"):
        company_id = order_data["TaskTypes"].get("company_id")
        if company_id:
            try:
                company_result = (
                    supabase.table("Companies")
                    .select("id, name")
                    .eq("id", company_id)
                    .limit(1)
                    .execute()
                )
                if company_result.data:
                    company = company_result.data[0]
                    order_info["company"] = {
                        "name": company.get("name"),
                        "id": company.get("id"),
                    }
            except Exception:
                pass
    return order_info


def parse_date_utc(date_str):
    if not date_str:
        return None
    try:
        if "T" in date_str:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def is_order_overdue(deadline_str, status=None):
    if not deadline_str or (status and status == "completed"):
        return False
    deadline_dt = parse_date_utc(deadline_str)
    if not deadline_dt:
        return False
    today = datetime.now(timezone.utc).date()
    return deadline_dt.date() < today

def kg_to_tons(weight_kg):
    if weight_kg is None:
        return 0.0
    try:
        return float(weight_kg) / 1000.0
    except (ValueError, TypeError):
        return 0.0


def calculate_statistics_by_task_type(orders, custom_task_types):
    stats = {}
    for task_type_id, task_type_name in custom_task_types.items():
        stats[task_type_id] = {"name": task_type_name, "tons": 0.0}
    for order in orders:
        task_type_id = order.get("task_type_id")
        weight = order.get("Weight") or order.get("weight")
        if task_type_id and task_type_id in custom_task_types:
            if task_type_id not in stats:
                stats[task_type_id] = {"name": custom_task_types[task_type_id], "tons": 0.0}
            stats[task_type_id]["tons"] += kg_to_tons(weight)
    return stats


def generate_available_months(all_orders):
    available_months = []
    if not all_orders:
        return available_months
    first_date = None
    for order in all_orders:
        order_date_str = order.get("created_at") or order.get("deadline")
        order_date = parse_date_utc(order_date_str)
        if order_date:
            if first_date is None or order_date < first_date:
                first_date = order_date
    if first_date:
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
        now = datetime.now(timezone.utc)
        current = datetime(first_date.year, first_date.month, 1, tzinfo=timezone.utc)
        end = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        while current <= end:
            month_str = f"{current.year}-{current.month:02d}"
            month_label = f"{month_names[current.month].capitalize()} {current.year}"
            available_months.append({"value": month_str, "label": month_label})
            if current.month == 12:
                current = datetime(current.year + 1, 1, 1, tzinfo=timezone.utc)
            else:
                current = datetime(current.year, current.month + 1, 1, tzinfo=timezone.utc)
        available_months.reverse()
    return available_months

