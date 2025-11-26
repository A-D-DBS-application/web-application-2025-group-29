"""
Smart Driver Assignment & Priority Scoring Algorithm

Dit algoritme helpt bedrijven om:
1. Bestellingen te prioriteren op basis van urgentie
2. Automatisch de beste chauffeur voor te stellen voor elke bestelling

Gebruikt eenvoudige scoring methoden die geschikt zijn voor handelsingenieurs.
"""

from datetime import datetime, timedelta, date
from typing import List, Dict, Optional

# Tijden per 1000 kg (in uren)
# Case-insensitive matching wordt gebruikt
TASK_TIMES_PER_1000KG = {
    'pletten': 1.0,
    'malen': 2.0,
    'zuigen': 0.5,
    'blazen': 0.5,
    'mengen': 1.0
}

# Standaard werkdag in uren
WORKDAY_HOURS = 10.0

# Reistijd naar nieuwe klant (in uren)
TRAVEL_TIME_HOURS = 1.0


def calculate_priority_score(order: Dict) -> float:
    """
    Bereken een prioriteitsscore voor een bestelling (0-100).
    Hogere score = urgenter.
    
    Factoren:
    - Deadline urgentie (hoe dichter bij deadline, hoe hoger)
    - Gewicht (zwaardere bestellingen = urgenter)
    - Leeftijd van bestelling (oudere bestellingen = urgenter)
    
    Args:
        order: Dictionary met order data (deadline, Weight, created_at, etc.)
    
    Returns:
        float: Priority score tussen 0 en 100
    """
    score = 0.0
    
    # Factor 1: Deadline urgentie (0-50 punten)
    if order.get('deadline'):
        try:
            deadline = datetime.strptime(order['deadline'], '%Y-%m-%d').date()
            today = datetime.now().date()
            days_until_deadline = (deadline - today).days
            
            if days_until_deadline < 0:
                # Deadline is verstreken - zeer urgent!
                score += 50
            elif days_until_deadline == 0:
                # Deadline is vandaag
                score += 45
            elif days_until_deadline <= 2:
                # Deadline binnen 2 dagen
                score += 40 - (days_until_deadline * 5)
            elif days_until_deadline <= 7:
                # Deadline binnen week
                score += 30 - (days_until_deadline * 2)
            else:
                # Deadline verder weg
                score += max(10, 20 - days_until_deadline)
        except (ValueError, TypeError):
            # Geen geldige deadline, gebruik standaard score
            score += 15
    else:
        # Geen deadline = minder urgent
        score += 10
    
    # Factor 2: Gewicht (0-30 punten)
    weight = order.get('Weight') or order.get('weight') or 0
    if weight:
        try:
            weight_float = float(weight)
            # Zwaarder = urgenter (max 30 punten bij 1000kg+)
            score += min(30, weight_float / 33.33)
        except (ValueError, TypeError):
            pass
    
    # Factor 3: Leeftijd van bestelling (0-20 punten)
    if order.get('created_at'):
        try:
            created_at = datetime.fromisoformat(order['created_at'].replace('Z', '+00:00'))
            days_old = (datetime.now(created_at.tzinfo) - created_at).days
            
            # Oudere bestellingen = urgenter (max 20 punten bij 7+ dagen oud)
            score += min(20, days_old * 2.86)
        except (ValueError, TypeError, AttributeError):
            pass
    
    return min(100.0, max(0.0, score))


def calculate_order_time_hours(order: Dict) -> float:
    """
    Bereken de totale tijd (in uren) die nodig is voor een bestelling.
    
    Args:
        order: Dictionary met order data (task_type, Weight, etc.)
    
    Returns:
        float: Totale tijd in uren (werk tijd + reistijd)
    """
    task_type = (order.get('task_type') or '').lower()
    weight = order.get('Weight') or order.get('weight') or 0
    
    try:
        weight_float = float(weight)
    except (ValueError, TypeError):
        weight_float = 0
    
    # Bepaal werk tijd per 1000 kg
    time_per_1000kg = TASK_TIMES_PER_1000KG.get(task_type, 1.0)  # Default 1 uur als onbekend
    
    # Bereken werk tijd
    work_time = (weight_float / 1000.0) * time_per_1000kg
    
    # Voeg reistijd toe
    total_time = work_time + TRAVEL_TIME_HOURS
    
    return total_time


def calculate_driver_workload_hours(driver_id: int, orders: List[Dict], target_date: Optional[date] = None) -> float:
    """
    Bereken hoeveel uren een chauffeur al geboekt heeft.
    
    Args:
        driver_id: ID van de chauffeur
        orders: Lijst van alle orders (inclusief die van deze chauffeur)
        target_date: Optionele datum om alleen taken op die dag te tellen
    
    Returns:
        float: Totaal aantal uren geboekt
    """
    total_hours = 0.0
    
    for order in orders:
        if order.get('driver_id') == driver_id and order.get('status') == 'accepted':
            # Als target_date is gegeven, check of deze order op die dag is
            if target_date:
                order_deadline = order.get('deadline')
                if order_deadline:
                    try:
                        deadline_date = datetime.strptime(order_deadline, '%Y-%m-%d').date()
                        if deadline_date != target_date:
                            continue  # Skip deze order, niet op target datum
                    except (ValueError, TypeError):
                        pass  # Als deadline niet parsebaar is, tel mee
            
            # Bereken tijd voor deze order
            order_time = calculate_order_time_hours(order)
            total_hours += order_time
    
    return total_hours


def calculate_driver_score(driver: Dict, order: Dict, driver_workload_hours: Dict[int, float], all_orders: List[Dict]) -> float:
    """
    Bereken een geschiktheidsscore voor een chauffeur voor een specifieke bestelling (0-100).
    Hogere score = beter geschikt.
    
    Factoren:
    - Beschikbare tijd op deadline dag (meer tijd = beter)
    - Huidige totale workload (minder uren = beter)
    - Past de nieuwe taak nog in de werkdag?
    
    Args:
        driver: Dictionary met driver data (id, name, etc.)
        order: Dictionary met order data (deadline, Weight, task_type, etc.)
        driver_workload_hours: Dictionary {driver_id: totaal_uren} met huidige workload
        all_orders: Lijst van alle orders om deadline matching te doen
    
    Returns:
        float: Driver suitability score tussen 0 en 100
    """
    score = 50.0  # Start met basis score
    driver_id = driver.get('id')
    
    if not driver_id:
        return 0.0
    
    # Bereken tijd nodig voor deze nieuwe order
    order_time = calculate_order_time_hours(order)
    
    # Bepaal deadline datum van de nieuwe order
    order_deadline_date = None
    if order.get('deadline'):
        try:
            order_deadline_date = datetime.strptime(order['deadline'], '%Y-%m-%d').date()
        except (ValueError, TypeError):
            pass
    
    # Bereken huidige workload op deadline dag (als deadline bekend is)
    if order_deadline_date:
        hours_on_deadline_day = calculate_driver_workload_hours(driver_id, all_orders, order_deadline_date)
        available_hours = WORKDAY_HOURS - hours_on_deadline_day
        
        # Factor 1: Past de taak nog op de deadline dag? (0-50 punten)
        if available_hours >= order_time:
            # Taak past perfect
            if available_hours >= order_time + 2:
                score += 50  # Veel ruimte
            elif available_hours >= order_time + 1:
                score += 40  # Goede ruimte
            else:
                score += 30  # Past precies
        else:
            # Taak past niet meer op deadline dag
            score -= 30  # Grote penalty
            return max(0.0, score)  # Return lage score, niet geschikt
    
    # Factor 2: Totale workload (0-30 punten)
    # Minder uren geboekt = hogere score
    total_hours = driver_workload_hours.get(driver_id, 0.0)
    if total_hours == 0:
        score += 30  # Geen taken = perfect beschikbaar
    elif total_hours <= 5:
        score += 25  # Weinig taken
    elif total_hours <= 10:
        score += 15  # Gemiddeld
    elif total_hours <= 20:
        score += 5  # Veel taken
    else:
        score -= 10  # Zeer druk
    
    # Factor 3: Deadline compatibiliteit bonus (0-20 punten)
    # Als deadline bekend is en er is ruimte, bonus
    if order_deadline_date:
        hours_on_deadline_day = calculate_driver_workload_hours(driver_id, all_orders, order_deadline_date)
        if hours_on_deadline_day == 0:
            score += 20  # Geen taken op die dag = perfect
        elif hours_on_deadline_day <= 5:
            score += 10  # Weinig taken op die dag
    
    return min(100.0, max(0.0, score))


def suggest_best_driver(drivers: List[Dict], order: Dict, driver_workload_hours: Dict[int, float], all_orders: List[Dict]) -> Optional[Dict]:
    """
    Stel de beste chauffeur voor voor een bestelling.
    
    Args:
        drivers: Lijst van beschikbare chauffeurs
        order: De bestelling waarvoor een chauffeur gezocht wordt
        driver_workload_hours: Dictionary {driver_id: totaal_uren} met huidige workload
        all_orders: Lijst van alle orders voor deadline matching
    
    Returns:
        Dict met driver info en score, of None als geen drivers beschikbaar
    """
    if not drivers:
        return None
    
    # Bereken tijd nodig voor deze order
    order_time = calculate_order_time_hours(order)
    order_deadline_date = None
    if order.get('deadline'):
        try:
            order_deadline_date = datetime.strptime(order['deadline'], '%Y-%m-%d').date()
        except (ValueError, TypeError):
            pass
    
    # Bereken score voor elke chauffeur
    driver_scores = []
    for driver in drivers:
        score = calculate_driver_score(driver, order, driver_workload_hours, all_orders)
        
        # Check of de taak past op de deadline dag
        if order_deadline_date:
            hours_on_deadline = calculate_driver_workload_hours(driver['id'], all_orders, order_deadline_date)
            if hours_on_deadline + order_time > WORKDAY_HOURS:
                # Taak past niet, skip deze chauffeur
                continue
        
        driver_scores.append({
            'driver': driver,
            'score': score
        })
    
    if not driver_scores:
        return None  # Geen geschikte chauffeurs gevonden
    
    # Sorteer op score (hoogste eerst)
    driver_scores.sort(key=lambda x: x['score'], reverse=True)
    
    # Return de beste chauffeur
    best = driver_scores[0]
    driver_id = best['driver']['id']
    total_hours = driver_workload_hours.get(driver_id, 0.0)
    
    # Bereken beschikbare tijd op deadline dag
    available_hours = WORKDAY_HOURS
    if order_deadline_date:
        hours_on_deadline = calculate_driver_workload_hours(driver_id, all_orders, order_deadline_date)
        available_hours = WORKDAY_HOURS - hours_on_deadline
    
    return {
        'driver_id': best['driver']['id'],
        'driver_name': best['driver'].get('name', 'Onbekend'),
        'score': best['score'],
        'reason': _get_suggestion_reason(best['score'], total_hours, available_hours, order_time)
    }


def _get_suggestion_reason(score: float, total_hours: float, available_hours: float, order_time: float) -> str:
    """Genereer een menselijke uitleg waarom deze chauffeur wordt voorgesteld."""
    if total_hours == 0:
        return f"Beschikbaar ({available_hours:.1f}u beschikbaar, taak: {order_time:.1f}u)"
    elif available_hours >= order_time + 2:
        return f"Goed beschikbaar ({available_hours:.1f}u beschikbaar, taak: {order_time:.1f}u)"
    elif available_hours >= order_time:
        return f"Beschikbaar ({available_hours:.1f}u beschikbaar, taak: {order_time:.1f}u)"
    else:
        return f"Beperkt beschikbaar ({available_hours:.1f}u beschikbaar, taak: {order_time:.1f}u)"


def sort_orders_by_priority(orders: List[Dict]) -> List[Dict]:
    """
    Sorteer bestellingen op prioriteit (urgentste eerst).
    
    Args:
        orders: Lijst van order dictionaries
    
    Returns:
        Gesorteerde lijst (urgentste eerst)
    """
    # Bereken priority score voor elke order
    orders_with_scores = []
    for order in orders:
        score = calculate_priority_score(order)
        orders_with_scores.append({
            'order': order,
            'priority_score': score
        })
    
    # Sorteer op score (hoogste eerst)
    orders_with_scores.sort(key=lambda x: x['priority_score'], reverse=True)
    
    # Voeg score toe aan order data en return
    result = []
    for item in orders_with_scores:
        order = item['order'].copy()
        order['priority_score'] = item['priority_score']
        result.append(order)
    
    return result

