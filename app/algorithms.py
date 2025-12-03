from datetime import datetime, date
from typing import List, Dict, Optional

WORKDAY_HOURS = 12.0
TRAVEL_TIME_HOURS = 0.75

def calculate_priority_score(order: Dict) -> float:
    score = 0.0
    if order.get('deadline'):
        try:
            deadline = datetime.strptime(order['deadline'], '%Y-%m-%d').date()
            today = datetime.now().date()
            days_until_deadline = (deadline - today).days
            
            if days_until_deadline < 0:
                score += 50
            elif days_until_deadline == 0:
                score += 45
            elif days_until_deadline <= 2:
                score += 40 - (days_until_deadline * 5)
            elif days_until_deadline <= 7:
                score += 30 - (days_until_deadline * 2)
            else:
                score += max(10, 20 - days_until_deadline)
        except (ValueError, TypeError):
            score += 15
    else:
        score += 10
    
    weight = order.get('Weight') or order.get('weight') or 0
    if weight:
        try:
            weight_float = float(weight)
            score += min(30, weight_float / 33.33)
        except (ValueError, TypeError):
            pass
    
    if order.get('created_at'):
        try:
            created_at = datetime.fromisoformat(order['created_at'].replace('Z', '+00:00'))
            days_old = (datetime.now(created_at.tzinfo) - created_at).days
            
            score += min(20, days_old * 2.86)
        except (ValueError, TypeError, AttributeError):
            pass
    
    return min(100.0, max(0.0, score))


def calculate_order_time_hours(order: Dict, custom_task_times: Optional[Dict[int, float]] = None) -> float:
    if order.get('_custom_time_per_1000kg'):
        time_per_1000kg = order['_custom_time_per_1000kg']
    else:
        task_type_id = order.get('task_type_id')
        
        if custom_task_times and task_type_id and task_type_id in custom_task_times:
            time_per_1000kg = custom_task_times[task_type_id]
        else:
            time_per_1000kg = 1.0
    
    try:
        weight_float = float(order.get('Weight') or order.get('weight') or 0)
    except (ValueError, TypeError):
        weight_float = 0
    
    work_time = (weight_float / 1000.0) * time_per_1000kg
    total_time = work_time + TRAVEL_TIME_HOURS
    
    return total_time


def calculate_driver_workload_hours(driver_id: int, orders: List[Dict], target_date: Optional[date] = None, custom_task_times: Optional[Dict[int, float]] = None) -> float:
    total_hours = 0.0
    
    for order in orders:
        if order.get('driver_id') == driver_id and order.get('status') == 'accepted':
            if target_date:
                order_deadline = order.get('deadline')
                if order_deadline:
                    try:
                        deadline_date = datetime.strptime(order_deadline, '%Y-%m-%d').date()
                        if deadline_date != target_date:
                            continue  
                    except (ValueError, TypeError):
                        pass
            
            order_time = calculate_order_time_hours(order, custom_task_times)
            total_hours += order_time
    
    return total_hours


def calculate_driver_score(driver: Dict, order: Dict, driver_workload_hours: Dict[int, float], all_orders: List[Dict], custom_task_times: Optional[Dict[int, float]] = None) -> float:
    driver_id = driver.get('id')
    if not driver_id:
        return 0.0
    
    order_time = calculate_order_time_hours(order, custom_task_times)
    
    order_deadline_date = None
    if order.get('deadline'):
        try:
            order_deadline_date = datetime.strptime(order['deadline'], '%Y-%m-%d').date()
        except (ValueError, TypeError):
            pass
    
    if not order_deadline_date:
        return 50.0
    
    hours_on_deadline_day = calculate_driver_workload_hours(driver_id, all_orders, order_deadline_date, custom_task_times)
    available_hours = WORKDAY_HOURS - hours_on_deadline_day
    
    if available_hours < order_time:
        return 0.0
    
    if available_hours >= order_time + 4:
        score = 100.0  # Veel ruimte
    elif available_hours >= order_time + 2:
        score = 80.0  # Goede ruimte
    elif available_hours >= order_time + 1:
        score = 70.0  # Voldoende ruimte
    else:
        score = 60.0  # Past precies, maar nog steeds geschikt
    
    return score

def suggest_best_driver(drivers: List[Dict], order: Dict, driver_workload_hours: Dict[int, float], all_orders: List[Dict], custom_task_times: Optional[Dict[int, float]] = None) -> Optional[Dict]:
    if not drivers:
        return None

    order_time = calculate_order_time_hours(order, custom_task_times)
    order_deadline_date = None
    if order.get('deadline'):
        try:
            order_deadline_date = datetime.strptime(order['deadline'], '%Y-%m-%d').date()
        except (ValueError, TypeError):
            pass

    driver_scores = []
    for driver in drivers:
        score = calculate_driver_score(driver, order, driver_workload_hours, all_orders, custom_task_times)

        if order_deadline_date:
            hours_on_deadline = calculate_driver_workload_hours(driver['id'], all_orders, order_deadline_date, custom_task_times)
            if hours_on_deadline + order_time > WORKDAY_HOURS:
                continue
        
        driver_scores.append({
            'driver': driver,
            'score': score
        })
    
    if not driver_scores:
        return None

    driver_scores.sort(key=lambda x: x['score'], reverse=True)

    best = driver_scores[0]
    driver_id = best['driver']['id']
    total_hours = driver_workload_hours.get(driver_id, 0.0)

    available_hours = WORKDAY_HOURS
    if order_deadline_date:
        hours_on_deadline = calculate_driver_workload_hours(driver_id, all_orders, order_deadline_date, custom_task_times)
        available_hours = WORKDAY_HOURS - hours_on_deadline
    
    return {
        'driver_id': best['driver']['id'],
        'driver_name': best['driver'].get('name', 'Onbekend'),
        'score': best['score'],
        'available_hours': available_hours,
        'reason': _get_suggestion_reason(best['score'], total_hours, available_hours, order_time)
    }


def _get_suggestion_reason(score: float, total_hours: float, available_hours: float, order_time: float) -> str:
    if available_hours >= order_time + 4:
        return f"Veel ruimte beschikbaar ({available_hours:.1f}u beschikbaar, taak: {order_time:.1f}u)"
    elif available_hours >= order_time + 2:
        return f"Goed beschikbaar ({available_hours:.1f}u beschikbaar, taak: {order_time:.1f}u)"
    elif available_hours >= order_time + 1:
        return f"Voldoende ruimte ({available_hours:.1f}u beschikbaar, taak: {order_time:.1f}u)"
    elif available_hours >= order_time:
        return f"Beschikbaar ({available_hours:.1f}u beschikbaar, taak: {order_time:.1f}u)"
    else:
        return f"Beperkt beschikbaar ({available_hours:.1f}u beschikbaar, taak: {order_time:.1f}u)"


def sort_orders_by_priority(orders: List[Dict]) -> List[Dict]:
    orders_with_scores = []
    for order in orders:
        score = calculate_priority_score(order)
        orders_with_scores.append({
            'order': order,
            'priority_score': score
        })
    
    orders_with_scores.sort(key=lambda x: x['priority_score'], reverse=True)
    
    result = []
    for item in orders_with_scores:
        order = item['order'].copy()
        order['priority_score'] = item['priority_score']
        result.append(order)
    
    return result


def filter_duplicate_orders(orders: List[Dict]) -> List[Dict]:
    if not orders:
        return []
    
    seen_orders = {}
    
    for order in orders:
        task_type_id = order.get('task_type_id')
        product_type = order.get('product_type', '')
        address_id = order.get('address_id')
        company_id = order.get('company_id')
        
        key = (
            task_type_id,
            str(product_type).lower().strip() if product_type else '',
            address_id,
            company_id
        )
                
        if key not in seen_orders:
            seen_orders[key] = order
    
    return list(seen_orders.values())

