# AgriFlow - Web Application MVP

AgriFlow is een webapplicatie voor het beheren van agrarische bestellingen en logistiek. Het platform verbindt klanten, bedrijven en chauffeurs om efficiënt bestellingen te plaatsen, te beheren en uit te voeren.

AgriFlow is ontwikkeld als Minimum Viable Product (MVP) voor het beheren van agrarische bestellingen. Het platform ondersteunt drie gebruikersrollen:

- **Klanten**: Plaatsen bestellingen, beheren adressen, bekijken order status
- **Bedrijven**: Beheren bestellingen, toewijzen chauffeurs, bekijken statistieken
- **Chauffeurs**: Bekijken toegewezen ritten, voltooien taken, selecteren bedrijf

Het systeem gebruikt intelligente algoritmes voor:
- Prioritering van bestellingen op basis van urgentie
- Automatische suggestie van de beste chauffeur voor elke bestelling
- Workload berekening en beschikbaarheidsanalyse


## Functionaliteiten

- **Registratie & Login**: Eenvoudige gebruikersnaam-gebaseerde authenticatie (geen wachtwoord vereist)
- **Profiel Beheer**: Klanten kunnen adressen beheren
- **Bestellingen Plaatsen**: Klanten kunnen bestellingen plaatsen met deadline, taaktype, producttype en gewicht
- **Eerdere Bestellingen Kopiëren**: Klanten kunnen voltooide bestellingen kopiëren (alleen deadline en gewicht aanpassen)
- **Bestellingen Beheren**: Klanten kunnen bestellingen bekijken, bewerken en annuleren (indien nog niet toegewezen)
- **Bedrijf Dashboard**: Overzicht van alle bestellingen met prioriteitsscores en chauffeur suggesties
- **Custom Taaktypes**: Bedrijven kunnen eigen taaktypes toevoegen met tijden per 1000kg
- **Chauffeur Toewijzing**: Bedrijven kunnen chauffeurs toewijzen aan bestellingen
- **Chauffeur Dashboard**: Chauffeurs zien hun toegewezen ritten met gewicht en werkduur, kunnen taken voltooien
- **Statistieken**: Bedrijven zien maandelijkse en jaarlijkse statistieken per taaktype en per chauffeur

## Algoritme Features

- **Priority Scoring**: Bestellingen worden automatisch gesorteerd op urgentie
- **Smart Driver Suggestion**: Systeem stelt automatisch de beste chauffeur voor op basis van beschikbaarheid
- **Workload Calculation**: Berekent beschikbare uren per chauffeur (12-urige werkdag)
- **Time Estimation**: Schat benodigde tijd per bestelling op basis van custom taaktype tijden en gewicht
- **Duplicate Filtering**: Filtert dubbele orders bij het kopiëren van eerdere bestellingen

## Installatie

Vereisten
- Python 3.8 of hoger
- pip (Python package manager)
- Supabase account (of gebruik de geconfigureerde database)

Stappen
1. **Clone de repository**
   ```bash
   git clone <repository-url>
   cd web-application-2025-group-29
   ```

2. **Maak een virtuele omgeving aan**
   ```bash
   # Windows
   python -m venv venv
   venv\Scripts\activate

   # macOS/Linux
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Installeer dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configureer environment variabelen**
   De applicatie werkt standaard met de geconfigureerde Supabase database. Als je een eigen database wilt gebruiken, maak een `.env` bestand aan:
   ```
   SECRET_KEY=your-secret-key-here
   SUPABASE_URL=https://your-project.supabase.co
   SUPABASE_KEY=your-supabase-key-here
   ```

5. **Database Setup**
   De database schema staat in `database_schema.sql`. Als je een nieuwe database gebruikt, voer dit script uit in je Supabase SQL editor of via psql.

6. **Start de applicatie**
   ```bash
   python run.py
   ```
   
   Of met een specifieke poort:
   ```bash
   python run.py 5000
   ```

7. **Open de applicatie**
   Navigeer naar `http://127.0.0.1:5001` (of de poort die je hebt opgegeven) in je browser.

## Gebruik

1. **Registreer een account**
   - Klik op "Registreren" in de navigatiebalk
   - Kies je gebruikersrol: Klant, Bedrijf, of Chauffeur
   - Voer je gebruikersnaam (email) en naam in
   - Geen wachtwoord vereist

2. **Log in**
   - Klik op "Inloggen"
   - Voer je gebruikersnaam (email) in
   - Je wordt automatisch doorgestuurd naar je dashboard

Voor Klanten
1. **Profiel instellen**
   - Ga naar "Profiel" in de navigatiebalk
   - Voeg adressen toe via "Adres toevoegen"

2. **Bestelling plaatsen**
   - Klik op "Plaats een bestelling" of ga naar de order pagina
   - Kies tussen "Nieuwe bestelling" of "Eerdere bestelling kopiëren"
   - Bij kopiëren: selecteer een voltooide bestelling (alleen deadline en gewicht aanpassen)
   - Bij nieuwe: selecteer een adres (of voeg er eerst een toe)
   - Kies een bedrijf (taaktypes worden dynamisch geladen)
   - Vul deadline, taaktype, producttype en gewicht in
   - Bevestig de bestelling

3. **Bestellingen beheren**
   - Ga naar "Mijn Bestellingen"
   - Bekijk actieve en voltooide bestellingen
   - Bewerk of annuleer bestellingen (indien nog niet toegewezen)

Voor Bedrijven
1. **Dashboard bekijken**
   - Na inloggen zie je automatisch het bedrijf dashboard
   - Overzicht van alle bestellingen, gesorteerd op prioriteit
   - Statistieken: totaal, pending, voltooide bestellingen

2. **Taaktypes beheren**
   - Ga naar "Profiel" in de navigatiebalk
   - Voeg custom taaktypes toe (bijv. "ploegen", "zaaien")
   - Stel tijd per 1000kg in voor elk taaktype
   - Verwijder taaktypes indien nodig

3. **Chauffeur toewijzen**
   - Voor elke bestelling zonder chauffeur zie je een suggestie
   - Selecteer een chauffeur uit de dropdown
   - Klik op "Toewijzen"
   - De bestelling wordt gemarkeerd als "accepted"

4. **Statistieken bekijken**
   - Ga naar "Statistieken" in de navigatiebalk
   - Bekijk maandelijkse statistieken (selecteer maand)
   - Bekijk jaarlijkse statistieken
   - Zie tonnen per taaktype en per chauffeur

5. **Prioriteitsscores**
   - Elke bestelling heeft een prioriteitsscore (0-100)
   - Bestellingen worden automatisch gesorteerd: hoogste prioriteit eerst
   - Score gebaseerd op: deadline urgentie, gewicht, leeftijd

Voor Chauffeurs
1. **Bedrijf selecteren** (eerste keer)
   - Na eerste login moet je een bedrijf selecteren
   - Kies het bedrijf waar je voor werkt

2. **Ritten bekijken**
   - Ga naar "Ritten" in de navigatiebalk
   - Zie actieve en voltooide ritten
   - Ritten tonen gewicht en werkduur (exclusief reistijd)
   - Ritten zijn gesorteerd op deadline

3. **Taak voltooien**
   - Klik op "Voltooien" bij een actieve rit
   - De status wordt automatisch bijgewerkt naar "completed"

## Algoritme

Priority Scoring
Het `calculate_priority_score()` algoritme berekent een prioriteitsscore (0-100) voor elke bestelling:

- **Deadline Urgentie (0-50 punten)**:
  - Verlopen deadline: +50 punten
  - Deadline vandaag: +45 punten
  - Deadline binnen 2 dagen: +40 tot +30 punten
  - Deadline binnen 7 dagen: +30 tot +16 punten
  - Deadline verder weg: +10 tot +20 punten

- **Gewicht (0-30 punten)**:
  - Zwaardere bestellingen krijgen hogere scores
  - Maximaal 30 punten voor zeer zware bestellingen

- **Leeftijd (0-20 punten)**:
  - Oudere bestellingen krijgen hogere scores
  - Maximaal 20 punten voor zeer oude bestellingen

Smart Driver Suggestion
Het `suggest_best_driver()` algoritme stelt automatisch de beste chauffeur voor:

- **Beschikbaarheid op Deadline Dag**:
  - Controleert of taak past binnen 12-urige werkdag
  - Alleen beschikbare uren op deadline dag worden meegenomen
  - Score gebaseerd op beschikbare ruimte (60-100 punten)

- **Workload**: Berekent totale uren per chauffeur voor geaccepteerde bestellingen op deadline dag

Time Calculation
- **Order Time**: Berekent benodigde tijd op basis van:
  - Custom taaktype tijden per 1000kg (instelbaar per bedrijf)
  - Gewicht van de bestelling
  - Reistijd: 0.75 uur per bestelling (standaard)
  - Fallback: 1.0 uur per 1000kg als geen custom tijd is ingesteld

- **Workload**: Berekent totale uren per chauffeur voor geaccepteerde bestellingen

Duplicate Filtering
Het `filter_duplicate_orders()` algoritme filtert dubbele orders bij het kopiëren:
- Orders zijn duplicaten als: task_type_id, product_type, address_id en company_id hetzelfde zijn
- Deadline en gewicht mogen verschillen
- Behoudt de meest recente order van elke groep duplicaten

**Implementatie**: Alle algoritmes zijn zelf geïmplementeerd in `app/algorithms.py` zonder gebruik van externe AI/ML APIs.

## Database Schema

De database bestaat uit de volgende tabellen:
- **Client**: Klant informatie (email, naam, achternaam)
- **Companies**: Bedrijf informatie
- **Drivers**: Chauffeur informatie, gekoppeld aan bedrijven
- **Address**: Klant adressen
- **TaskTypes**: Custom taaktypes per bedrijf met tijd per 1000kg
- **Orders**: Bestellingen met status tracking (pending, accepted, completed), gekoppeld aan TaskTypes

Zie `database_schema.sql` voor het volledige DDL schema met constraints, indexen en comments.

## ERD Model
Het Entity Relationship Diagram is beschikbaar in: ![alt text](<ERD model.png>)

## Project Structuur

web-application-2025-group-29/
├── app/
│   ├── __init__.py          # Flask app factory
│   ├── config.py            # Configuratie en Supabase setup
│   ├── routes.py            # Alle routes en functionaliteiten
│   ├── algorithms.py        # Priority scoring en driver suggestion algoritmes
│   └── templates/           # HTML templates
│       ├── base.html        # Base template
│       ├── login.html
│       ├── signup.html
│       ├── home.html
│       ├── profile.html
│       ├── order.html
│       ├── customer_orders.html
│       ├── edit_order.html
│       ├── company_dashboard.html
│       ├── company_statistics.html
│       ├── driver_dashboard.html
│       └── driver_select_company.html
├── database_schema.sql      # DDL schema
├── requirements.txt         # Python dependencies
├── run.py                   # Application entry point
├── README.md                # Dit bestand
└── AgriFlow_userstories.pdf # User stories documentatie

## Feedback Sessies

Tijdens de ontwikkeling hebben we regelmatig feedback verzameld van onze externe partner. Hieronder vind je de opnames van de feedback sessies:

Feedback Sessie 1
- **Datum**: 16/11/2025
- **Link**: [VOEG LINK TOE NAAR AUDIO/VIDEO OPNAME]

Feedback Sessie 2
- **Datum**: 30/11/2025
- **Link**: [VOEG LINK TOE NAAR AUDIO/VIDEO OPNAME]


Feedback Sessie 3 (indien van toepassing)
- **Datum**: 14/11/2025
- **Link**: [VOEG LINK TOE NAAR AUDIO/VIDEO OPNAME]

## UI Prototype
Het UI prototype is ontwikkeld in Figma en getest met potentiële gebruikers voordat de implementatie begon.

**Figma Link**: https://cake-ranch-12974397.figma.site/

## Render link
https://web-application-2025-group-29.onrender.com

## Kanban Board

Tijdens de ontwikkeling hebben we gebruik gemaakt van een Kanban board voor project management en sprint planning.

**Kanban Board Link**: [VOEG LINK TOE NAAR KANBAN BOARD]

## Team

**Groep 29**

- Senne Beyl - [Rol/Verantwoordelijkheid]
- Laurien Deroo - [Rol/Verantwoordelijkheid]
- Gaëtan Hanet - [Rol/Verantwoordelijkheid]
- Maxime Ramon - [Rol/Verantwoordelijkheid]
- Mathis Van Camp - [Rol/Verantwoordelijkheid]

**Externe Partner**: Gerd Deroo