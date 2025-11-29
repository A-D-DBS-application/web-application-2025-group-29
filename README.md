[![Review Assignment Due Date](https://classroom.github.com/assets/deadline-readme-button-22041afd0340ce965d47ae6ef1cefeee28c7c493a6346c4f15d667ab976d596c.svg)](https://classroom.github.com/a/DxqGQVx4)

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
- **Bestellingen Beheren**: Klanten kunnen bestellingen bekijken, bewerken en annuleren (indien nog niet toegewezen)
- **Bedrijf Dashboard**: Overzicht van alle bestellingen met prioriteitsscores en chauffeur suggesties
- **Chauffeur Toewijzing**: Bedrijven kunnen chauffeurs toewijzen aan bestellingen
- **Chauffeur Dashboard**: Chauffeurs zien hun toegewezen ritten en kunnen taken voltooien
- **Statistieken**: Bedrijven zien overzichten van totaal, pending en voltooide bestellingen

## Algoritme Features

- **Priority Scoring**: Bestellingen worden automatisch gesorteerd op urgentie
- **Smart Driver Suggestion**: Systeem stelt automatisch de beste chauffeur voor
- **Workload Calculation**: Berekent beschikbare uren per chauffeur
- **Time Estimation**: Schat benodigde tijd per bestelling op basis van taaktype en gewicht

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
   - Selecteer een adres (of voeg er eerst een toe)
   - Kies een bedrijf
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

2. **Chauffeur toewijzen**
   - Voor elke bestelling zonder chauffeur zie je een suggestie
   - Selecteer een chauffeur uit de dropdown
   - Klik op "Toewijzen"
   - De bestelling wordt gemarkeerd als "accepted"

3. **Prioriteitsscores**
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
   - Ritten zijn gesorteerd op deadline

3. **Taak voltooien**
   - Klik op "Voltooien" bij een actieve rit
   - De status wordt automatisch bijgewerkt naar "completed"

## Algoritme

Het AgriFlow platform gebruikt verschillende algoritmes voor intelligente besluitvorming:

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

- **Beschikbaarheid op Deadline Dag (0-50 punten)**:
  - Controleert of taak past binnen 10-urige werkdag
  - Bonus voor veel beschikbare ruimte

- **Totale Workload (0-30 punten)**:
  - Chauffeurs met minder taken krijgen hogere scores
  - Geen taken = +30 punten bonus

- **Deadline Compatibiliteit (0-20 punten)**:
  - Bonus als chauffeur geen/weinig taken heeft op deadline dag

Time Calculation
- **Order Time**: Berekent benodigde tijd op basis van:
  - Taaktype (pletten: 1u/1000kg, malen: 2u/1000kg, zuigen/blazen: 0.5u/1000kg, mengen: 1u/1000kg)
  - Gewicht
  - Reistijd: 0.75 uur per bestelling

- **Workload**: Berekent totale uren per chauffeur voor geaccepteerde bestellingen

**Implementatie**: Alle algoritmes zijn zelf geïmplementeerd in `app/algorithms.py` zonder gebruik van externe AI/ML APIs.

## Database Schema

De database bestaat uit de volgende tabellen:
- **Client**: Klant informatie (email, naam, achternaam)
- **Companies**: Bedrijf informatie
- **Drivers**: Chauffeur informatie, gekoppeld aan bedrijven
- **Address**: Klant adressen
- **Orders**: Bestellingen met status tracking (pending, accepted, completed)

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
│       ├── Base.HTML        # Base template
│       ├── login.html
│       ├── signup.html
│       ├── home.html
│       ├── profile.html
│       ├── order.html
│       ├── customer_orders.html
│       ├── edit_order.html
│       ├── company_dashboard.html
│       ├── driver_dashboard.html
│       └── driver_select_company.html
├── database_schema.sql      # DDL schema
├── requirements.txt         # Python dependencies
├── run.py                   # Application entry point
├── README.md                # Dit bestand
└── AgriFlow_userstories.docx # User stories documentatie

## Feedback Sessies

Tijdens de ontwikkeling hebben we regelmatig feedback verzameld van onze externe partner. Hieronder vind je de opnames van de feedback sessies:

### Feedback Sessie 1
- **Datum**: [VOEG DATUM TOE]
- **Link**: [VOEG LINK TOE NAAR AUDIO/VIDEO OPNAME]

### Feedback Sessie 2
- **Datum**: [VOEG DATUM TOE]
- **Link**: [VOEG LINK TOE NAAR AUDIO/VIDEO OPNAME]


### Feedback Sessie 3 (indien van toepassing)
- **Datum**: [VOEG DATUM TOE]
- **Link**: [VOEG LINK TOE NAAR AUDIO/VIDEO OPNAME]

**Opmerking**: Upload de feedback opnames naar Google Drive, YouTube (unlisted), of een andere cloud service en voeg de links hierboven toe.

## UI Prototype
Het UI prototype is ontwikkeld in Figma en getest met potentiële gebruikers voordat de implementatie begon.

- **Prototype Link**: [VOEG LINK TOE NAAR PROTOTYPE]
- **Screenshots**: Zie `screenshots/` folder voor screenshots van de uiteindelijke applicatie

**Opmerking**: Als je een UI prototype hebt gemaakt, voeg hier de link toe. Als je alleen de uiteindelijke applicatie hebt, verwijder deze sectie of pas aan.

## Kanban Board

Tijdens de ontwikkeling hebben we gebruik gemaakt van een Kanban board voor project management en sprint planning.

- **Kanban Board Link**: [VOEG LINK TOE NAAR KANBAN BOARD]

**Opmerking**: Als je GitHub Projects, Trello, Jira, of een ander tool hebt gebruikt, voeg hier de link toe. Als je geen Kanban board hebt gebruikt, verwijder deze sectie.

## Team

**Groep 29**

- [Team lid 1 naam] - [Rol/Verantwoordelijkheid]
- [Team lid 2 naam] - [Rol/Verantwoordelijkheid]
- [Team lid 3 naam] - [Rol/Verantwoordelijkheid]
- [Team lid 4 naam] - [Rol/Verantwoordelijkheid]

**Externe Partner**: [Gerd Deroo]