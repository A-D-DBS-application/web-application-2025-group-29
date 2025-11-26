# Smart Driver Assignment & Priority Scoring Algorithm

## Overzicht

Dit algoritme helpt bedrijven in AgriFlow om:
1. **Bestellingen te prioriteren** op basis van urgentie (deadline, gewicht, leeftijd)
2. **Automatisch de beste chauffeur voor te stellen** voor elke bestelling op basis van beschikbaarheid

## Technische Details

### Priority Scoring
Het algoritme berekent een prioriteitsscore (0-100) voor elke bestelling op basis van:
- **Deadline urgentie** (0-50 punten): Hoe dichter bij de deadline, hoe hoger de score
- **Gewicht** (0-30 punten): Zwaardere bestellingen krijgen hogere prioriteit
- **Leeftijd** (0-20 punten): Oudere bestellingen krijgen hogere prioriteit

### Smart Driver Suggestion
Het algoritme berekent een geschiktheidsscore (0-100) voor elke chauffeur op basis van:
- **Beschikbare tijd op deadline dag** (0-50 punten): Controleert of de taak past binnen de 10-urige werkdag
- **Totale workload** (0-30 punten): Chauffeurs met minder uren geboekt krijgen hogere scores
- **Deadline compatibiliteit** (0-20 punten): Bonus als chauffeur geen/weinig taken heeft op deadline dag

### Tijdsberekening
Het algoritme berekent de werkelijke tijd per bestelling:
- **Werk tijd**: Afhankelijk van taaktype en gewicht (per 1000 kg):
  - Pletten: 1 uur
  - Malen: 2 uur
  - Zuigen: 0.5 uur
  - Blazen: 0.5 uur
  - Mengen: 1 uur
- **Reistijd**: 1 uur per bestelling (naar nieuwe klant)
- **Werkdag**: Maximaal 10 uur per dag

## Implementatie

### Bestanden
- `app/algorithms.py`: Bevat alle algoritme logica
- `app/routes.py`: Integreert het algoritme in het bedrijf dashboard
- `app/templates/company_dashboard.html`: Toont prioriteitsscores en chauffeur suggesties

### Gebruikte Libraries
- **Geen externe ML/AI libraries**: Het algoritme gebruikt alleen standaard Python (datetime, typing)
- **Eenvoudige scoring methoden**: Geschikt voor handelsingenieurs zonder diepe programmeerkennis

### Core Logic
Het algoritme is volledig zelf geïmplementeerd:
- Feature engineering: Deadline parsing, gewicht normalisatie, workload berekening
- Scoring: Eenvoudige gewogen sommen met thresholds
- Ranking: Sorteren op scores

## Gebruik

1. **Automatische prioritering**: Bestellingen worden automatisch gesorteerd op urgentie
2. **Chauffeur suggesties**: Voor bestellingen zonder chauffeur wordt automatisch de beste chauffeur voorgesteld op basis van:
   - Beschikbare tijd op deadline dag
   - Totale workload
   - Of de taak past binnen de werkdag (10 uur)
3. **Visual feedback**: 
   - Prioriteitsscores worden getoond met kleurcodes (🔴 hoog, 🟡 medium, 🔵 laag)
   - Voorgestelde chauffeurs worden gemarkeerd met ⭐ in de dropdown
   - Geschatte tijd per bestelling wordt getoond
   - Beschikbare tijd per chauffeur wordt getoond in suggesties

## Toekomstige Uitbreidingen

Mogelijke verbeteringen (niet geïmplementeerd):
- Locatie-gebaseerde matching (afstand tussen chauffeur en bestemming)
- Historische performance data (welke chauffeur is het beste voor welk type taak)
- Machine learning voor betere voorspellingen (als meer data beschikbaar is)

## Documentatie

Het algoritme is volledig gedocumenteerd met docstrings en comments in het Nederlands, passend bij de doelgroep (handelsingenieurs).

