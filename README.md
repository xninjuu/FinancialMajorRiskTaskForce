# FMR-TaskForce Codex

Financial Major Risk Task Force (FMR) Codex ist ein geplantetes .NET-8-/WPF-System für nahezu Echtzeit-Transaktionsmonitoring, regelbasiertes Risikoscoring und leichtgewichtiges Case-Management.

## Zielbild & Kernfunktionen
- Transaktions-Streaming (API/Files) mit Near-Real-Time-Verarbeitung
- Risikoindikatoren für AML, Fraud, Terrorismusfinanzierung (TF) und Steuerbetrug
- Konfigurierbare Axiome ("Wenn… dann…", Gewichte, Thresholds) mit Szenario-Profilen
- Risk Engine / Axiom Engine mit Score-Normalisierung (0–100) und Alert-Thresholds
- Case-Management Light (Alerts bündeln, Status Open/Investigating/Closed)
- Echtzeit-News-Ticker für Financial Crime/Sanctions Headlines
- Reporting & Dashboards inkl. Heatmaps, CSV/PDF-Export
- Firmen-Website (Next.js) im identischen Schwarz-Rot-Weiß Look & Feel

## Architekturübersicht (Layered + MVVM)
- **Presentation (WPF/WinUI, MVVM)**: Dashboard, News-Ticker, Transaktionsstream, Alerts/Cases, Settings.
- **Application Services**: `RiskEngineService`, `TransactionIngestionService`, `NewsService`, `CaseManagementService`.
- **Domain**: Entities `Customer`, `Account`, `Transaction`, `RiskIndicator`, `Alert`, `Case`; Services `RiskScoringEngine`, `TypologyService`.
- **Infrastructure**: EF Core (SQLite → optional PostgreSQL/MSSQL), API-Clients (News, Sanktionslisten), Logging/Config.

### Datenmodell (Kurzfassung)
```csharp
public enum RiskDomain { MoneyLaundering, Fraud, TerroristFinancing, TaxEvasion }

public class Customer
{
    public Guid Id { get; set; }
    public string CustomerId { get; set; } = "";
    public string Name { get; set; } = "";
    public string Country { get; set; } = "";
    public bool IsPEP { get; set; }
    public decimal AnnualDeclaredIncome { get; set; }
}

public class Account
{
    public Guid Id { get; set; }
    public string AccountNumber { get; set; } = "";
    public Guid CustomerId { get; set; }
    public Customer Customer { get; set; } = null!;
}

public class Transaction
{
    public Guid Id { get; set; }
    public Guid AccountId { get; set; }
    public Account Account { get; set; } = null!;
    public DateTime Timestamp { get; set; }
    public decimal Amount { get; set; }
    public string Currency { get; set; } = "EUR";
    public string CounterpartyCountry { get; set; } = "";
    public string Channel { get; set; } = ""; // Online, Branch, Crypto, ...
    public bool IsCredit { get; set; }
}
```

### Risk-Logik & Scoring
```csharp
public class RiskIndicator
{
    public Guid Id { get; set; }
    public string Code { get; set; } = ""; // z.B. AML_HIGH_RISK_COUNTRY
    public string Description { get; set; } = "";
    public RiskDomain Domain { get; set; }
    public double Weight { get; set; }
}

public class EvaluatedIndicator
{
    public RiskIndicator Indicator { get; set; } = null!;
    public bool IsHit { get; set; }
    public double ScoreContribution => IsHit ? Indicator.Weight : 0.0;
}

public class RiskScoringEngine
{
    private readonly IList<RiskIndicator> _indicators;

    public (double score, IList<EvaluatedIndicator> hits) ScoreTransaction(Transaction tx)
    {
        var evaluated = new List<EvaluatedIndicator>();
        foreach (var ind in _indicators)
        {
            bool hit = EvaluateIndicator(ind, tx);
            evaluated.Add(new EvaluatedIndicator { Indicator = ind, IsHit = hit });
        }

        double raw = evaluated.Sum(e => e.ScoreContribution);
        double normalized = 100.0 / (1.0 + Math.Exp(-0.1 * (raw - 10))); // Logistische Transformation
        return (normalized, evaluated);
    }

    private bool EvaluateIndicator(RiskIndicator indicator, Transaction tx)
    {
        return indicator.Code switch
        {
            "AML_HIGH_RISK_COUNTRY" => tx.CounterpartyCountry is "IR" or "KP" or "AF",
            "AML_STRUCTURING" => false, // benötigt Historie
            _ => false
        };
    }
}
```
- Schwellenwerte: <30 Low, 30–60 Medium, >60 High → Alert.
- Axiome/Weights werden konfigurierbar gehalten (DB-Tabelle, optional UI-Editor).

### Beispiel-Indikatoren je Bereich
- **AML**: Hochrisiko-Länder, Smurfing/Structuring, Cash-Intensität vs. Profil, Hochrisiko-Produkte (Crypto/Prepaid), häufige internationale Transfers.
- **TF**: Spenden an NPOs/Regionen mit TF-Risiko, Kleinvolumige Serien in Konfliktgebiete, Layering ohne wirtschaftlichen Grund.
- **Fraud**: Hohe Chargeback-Rate, Device/KYC-Mismatch, verdächtige Refund-Muster, schnelle Konto-Leerung.
- **Tax Fraud**: Diskrepanz Einkommen vs. Zahlungsströme, Zahlungen in steuerlich günstige Jurisdiktionen, künstliche Verluste, komplexe Intercompany-Ketten.

## News-Service (Ticker)
- Pollt z.B. NewsAPI.org, TheNewsAPI, GNews oder NewsData.io über `HttpClient`.
- Keywords: "money laundering" OR "fraud" OR "terrorist financing".
- JSON → `NewsItem` (Titel, Quelle, PublishedAt, Url); aktualisiert ObservableCollection im UI.

## UI/Design Leitlinien (Schwarz–Rot–Weiß)
- Dark Anthrazit Hintergrund, Akzent Rot (#E50914), klare Sans-Serif (Segoe UI/Roboto/SF-ähnlich).
- Layout: Top News-Ticker, linke Navigation (Dashboard, Transactions, Alerts, Cases, Settings), zentrale KPIs, rechte Live-Transaktionsliste mit Farbcodes.
- Kartenbasiertes Dashboard, Buttons "Open Case" / "Mark False Positive" in Transaction-Detail.

### Ausführliches UI-Design (WPF/WinUI)
- **Design-Tokens**: Primär #0E0E10, Sekundär #16161A, Akzent Rot #E50914, Success #0FBF61, Warn #F2A007, Error #F05454; Border-Radius 10px, Schatten dezent (Blur 12, Opacity 18%).
- **Typografie**: Segoe UI/Inter 14pt normal; Headlines 22–28pt Semibold, Zahlen/KPIs 32pt Bold, Monospace (Cascadia) für Codes/IDs.
- **Dashboard-Layout (Grid 12)**:
  - Row 1: News-Ticker (scrollend), globale Filter (Zeitraum, Szenario-Profil, Domain-Toggles AML/Fraud/TF/Tax).
  - Row 2–3: KPI-Kacheln (Total Tx, Alerts High/Medium, Offene Cases, High-Risk-Share, PEP-Hits). Farbcode per Status.
  - Row 4–6: Links Heatmap (Country x Domain), Mitte Alert-Timeline, Rechts Live-Transaktionsliste mit Score-Badge.
  - Drawer rechts: Transaction-Detail mit Hit-Liste (Axiom + Weight + Begründung) und Action-Bar (Open Case, Mark False Positive, Export CSV/PDF).
- **Alert- & Case-Microcopy**: Jede Alert-Zeile zeigt max. zwei Axiom-Rationales (z.B. „AML_STRUCTURING – viele kleine Buchungen“) und Kontext (Kanal/Land) für schnellere Triagierung.
- **Design-Dichte**: Zwei Dichte-Stufen (Comfort/Compact) mit 12/8 px Padding, konsistent via `SpacingScale` in ResourceDictionary, inkl. Tabellen und Flyouts.
- **Insight Panels**: Rechtseitiges Insight-Panel fasst Score-Verlauf (Sparkline), Domain-Breakdown, Top-Axiome und Case-Historie zusammen; identische Struktur wie Konsolen-Dashboard.
- **Transactions View**: Sticky Filterbar (Amount Range, Domain, Device/Channel, Country), Tabellenlayout mit Color Badge je Score-Level, Inline-Button „Score erklären“ öffnet Sidepanel mit angewendeten Axiomen.
- **Cases View**: Kanban-ähnliche Spalten (Open/Investigating/Closed), Karten mit Case-ID, Kunde/Account, Alert-Count, letzte Aktivität, Quick-Actions (Assign, Close, Add Note).
- **Settings**: Axiom-/Weight-Editor (DataGrid mit Slider je Weight, Toggle aktiv/inaktiv), API-Key-Management (News, Sanktionslisten), Export-Vorlagen.
- **Motion/States**: Hover-Farben leicht aufgehellt, Fokus-Ring 2px Rot, Toasts oben rechts für neue Alerts/Cases, Live-Badge blinkt dezent.
- **Accessibility**: Farbkontrast > 4.5:1, Tastaturnavigation (Tab/Shift+Tab), ARIA-Live für News/Alerts in Web-Variante, „High Contrast“-Schalter.

### Near-Realtime Console UI (Prototyp)
- 200er Sliding-Window Statistik (aktueller Score, Mittelwert, High-Share) plus Case-Status-Breakdown.
- Domain-Breakdown und Top-Axiome (Trefferzählung) werden in festen Abständen (alle 8 Transaktionen) ausgegeben.
- News-Ticker rotiert Headlines; lässt sich in WPF via `ItemsControl` + `Storyboard` nachbilden.

## Zugriff & Sicherheit (Login, 2FA, Welcome Mail)
- Interner Zugriff als Default: Die Runtime ist als "Internal Only" markiert und blockiert öffentliche Nutzung.
- Bei Start wird ein Operator (`operator@fmr-taskforce.local`) registriert, ein sicheres Passwort generiert, ein 6-stelliger 2FA-Code ausgegeben und eine Welcome-Mail in der Konsole protokolliert.
- Der Login erfolgt nur bei gültigem Passwort **und** korrektem 2FA-Code; andernfalls schlägt der Session-Aufbau fehl.
- `AccessScope` markiert Objekte/Services als `PUBLIC` oder `INTERNAL_ONLY` und schützt die Echtzeit-Funktionen.
- **Pflichtsicherungen**: Account-Lockout nach 5 Fehlversuchen (5 Minuten Sperre), 15-Minuten-Session-TTL mit erzwungenem Re-Login, Audit-Log für alle Auth-/Access-Ereignisse, Ressourcenkatalog (Realtimestream, Risk Engine, Case Management) mit Internal-Only-Gate; News-Ticker bleibt Public.

## Reporting & Dashboards
- KPIs nach Domain (AML/TF/Fraud/Tax), Risikolevel Low/Medium/High.
- Heatmaps nach Kunde, Land, Produkt, Kanal.
- Exporte als CSV/PDF.

## Roadmap (Projekt Durchleitung)
1) **Fundament (MVP)**: Solution (.NET 8 WPF), Domain-Modelle, SQLite + EF Core, Basis-Indicators AML/Fraud, Simulation/Stream.
2) **Vertiefung**: TF/Tax-Indikatoren, UI-bearbeitbare Axiome, Case-Management mit Audit Trail.
3) **Echtzeit-News**: News-Service integrieren, UI-Ticker; optional Sanktions-/PEP-Quellen.
4) **Website & Branding**: Next.js Landing Page in gleicher CI.
5) **Hardening & Deployment**: Security/Secrets, Performance-Tests, Self-contained EXE Publish.

## Erweiterbarkeit / ML-Anbindung
- Python- oder ML-Pipeline kann über gRPC/REST angebunden werden (Feature Store, Anomaly Detection).
- Hybrid-Ansatz: regelbasiertes Scoring + ML-Modelle, die zusätzliche Features/Indikatoren liefern.

## Technologie-Empfehlung
- **Option A (präferiert)**: .NET 8, C#, WPF/WinUI 3, EF Core, SQLite (lokal), später PostgreSQL/MSSQL.
- **Option B**: Python + Qt/PySide + PyInstaller (mehr DS-Flexibilität, mehr UI-Aufwand).

## Near-Realtime Python-Simulation (Startpunkt)
Da die ursprüngliche .NET-Umgebung in diesem Workspace nicht verfügbar ist, liegt nun ein sofort ausführbarer Python-Prototyp bei, der alle Kernfunktionen simuliert:

- Transaktions-Streaming mit realistischeren Szenarien (Structuring, Konfliktregionen, Offshore-Spikes, Crypto-Mixer-Bursts, Refund-Carousels, Aid-Corridor-Spendenstory, Alltagsverkehr).
- Erweiterte Axiom-Engine mit PEP-Hits, Velocity-Spending, Income-Mismatch sowie neuen Regeln für Cash-Intensität, strukturierte Kleinspenden (TF), Aid-Corridor-Routen und Offshore-Hopping (Tax).
- **Konfigurierbare Regeln**: `config/indicators.json` und `config/thresholds.json` können ohne Codeänderung angepasst werden; die Engine lädt Gewichte/Thresholds zur Laufzeit und validiert das Schema beim Start (bricht sauber ab, falls ungültig).
- **Persistenz (SQLite)**: Alle Transaktionen, Alerts und Cases werden in `codex.db` abgelegt; die Historie pro Account wird für Structuring-/Velocity-Regeln verwendet. Schema-Version wird bei Start geprüft (Drop & Recreate für Proto-Versionen).
- **Mini-UI**: Ein schlanker, interner Web-View unter http://localhost:8000 listet Alerts; http://localhost:8000/cases zeigt Cases (read-only) – Basic Auth via `CODEX_DASHBOARD_USER` / `CODEX_DASHBOARD_PASSWORD`.
- Konsolen-Dashboard mit KPI-Zwischenständen (verarbeitete TX, Alerts, Flags, Domain-Breakdown, Top-Axiome) plus Sektion „Letzte Alerts“ mit Indikator-Erklärungen.
- Login-/2FA-Pflicht: Sicherheits-Bootstrap erzeugt Nutzer + Passwort + 2FA-Code, versendet Welcome-Mail und erzwingt "Internal Only"-Modus, bevor Streaming und Risk Engine starten.

### Architektur (ASCII)
```
[Ingestion] -> [Risk Engine] -> [Alerts] -> [Case Mgmt]
    |             |               |            |
    |             |               |            +-> SQLite (cases, notes)
    |             |               +-> SQLite (alerts, rationales)
    |             +-> Config (indicators.json, thresholds.json, validated)
    +-> SQLite (transactions, history windows)

[NewsService] -> [Console Dashboard]
[Dashboard Server (Basic Auth)] -> /alerts, /cases (read-only)
```

### Quickstart (Desktop GUI)
1) Voraussetzungen: Python 3.11+ und eine aktivierte venv.
2) Installiere Abhängigkeiten:
   ```bash
   pip install -r requirements.txt
   ```
3) Starte die GUI lokal:
   ```bash
   python -m app.main
   ```
   - Der Login-Dialog erzwingt Benutzer/Passwort (Admin wird bei Erststart angelegt; Passwort via Konsole ausgeben oder per ENV `CODEX_ADMIN_PASSWORD`).
   - Die GUI läuft offline; es wird **kein** Webserver gestartet.
4) Tests: `python -m pytest`

### Investigator-Tools (Desktop)
- Evidence-Locker mit Hashing/Sealing (Tab "Evidence")
- Case-Compare & Alert-Cluster-View für Überschneidungen
- Actor-Dashboard mit Basislinien/Counts je Kunde
- Netzwerk-Graph mit Korrelationen + Timeline-Dialog
- Forensic-Export (JSON/PDF/ZIP) inkl. Hash-Logging

### Windows: Einzelne EXE mit PyInstaller (GUI)
Voraussetzungen: Aktivierte venv (`.venv\\Scripts\\activate`), Abhängigkeiten installiert (`pip install -r requirements.txt`).

1) Build anstoßen (aus dem Repo-Root):
   ```powershell
   pyinstaller --clean --noconfirm FMR_TaskForce_GUI.spec
   ```
   Der Build legt `dist/FMR_TaskForce_GUI.exe` an.

2) Start per Doppelklick oder per `start_gui.bat` (Root des Repos):
   ```bat
   start_gui.bat
   ```
   Das Batch-Skript hält das Fenster offen und meldet Fehler klar.

3) Laufzeitpfade:
   - Configs (`indicators.json`, `thresholds.json`) werden aus `config/` neben der EXE oder aus dem eingebetteten Bundle gelesen. Optional kann `CODEX_CONFIG_DIR` gesetzt werden.
   - SQLite-DB: Standard `codex.db` liegt neben der EXE (oder via `CODEX_DB_PATH`).
   - `CODEX_ADMIN_PASSWORD` kann gesetzt werden, um den initialen Admin-User deterministisch anzulegen; andernfalls wird ein Zufallspasswort in der Konsole ausgegeben.

#### Schritt-für-Schritt (Portfolio-tauglich)
```bash
git clone <repo-url>
cd FinancialMajorRiskTaskForce
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt  # falls vorhanden, sonst pytest installieren
python -m pytest
python -m app.main
```

**Demo-Login (GUI, Admin-Bootstrap)**
- User: `admin`
- Passwort: via ENV `CODEX_ADMIN_PASSWORD` oder zufällig generiert beim ersten Start (wird in der Konsole angezeigt).
- Nutzerverwaltung liegt in SQLite (`users`-Tabelle). Rollen: ANALYST, LEAD, ADMIN (RBAC erzwingt Zugriffsrechte im UI).

### Demo-Flow (Story)
- **Problemstellung**: Near-Realtime AML/TF/Fraud/Tax-Risikoerkennung mit Case-Management-Light.
- **Scenario Examples**: Structuring/Smurfing, PEP mit Offshore-Layering, NGO-Spenden in Konfliktkorridoren, Dual-Use-Lieferungen, Card-Not-Present-Velocity.
- **Flow**: Ingestion liefert Szenarien → Risk Engine bewertet Indikatoren (Config-validiert) → High-Risk erzeugt Alerts → Alerts werden Cases zugeordnet (Status OPEN/IN_REVIEW/ESCALATED/CLOSED, Label z.B. SAR_FILED) → Notes und Audit landen in SQLite → Desktop-UI zeigt gefilterte Alerts/Cases mit RBAC.

Die Web-Ansicht ist read-only und lauscht auf Port 8000, solange der Prozess läuft.

Die Simulation erzeugt fortlaufend Transaktionen, berechnet Scores und druckt Alerts/Cases sowie den News-Ticker auf die Konsole. Die Axiome/Indikatoren findest du in `app/risk_engine.py`, die Streams/Beispiele in `app/ingestion.py` und `app/news_service.py`. Das Konsolen-Dashboard wird alle acht Transaktionen aktualisiert und zeigt Domain-Breakdowns sowie Hit-Statistiken.

### Sicherheits-Bootstrap beobachten
Beim Start erscheinen im Terminal:
- `[MAIL] ...` mit der Welcome-Mail inklusive generiertem Passwort und 2FA-Code (zur Demo-Ausgabe),
- `[AUTH]` Meldungen für den Session-Aufbau und
- `[ACCESS] Internal-only runtime verified` als Nachweis, dass interne Ressourcen geschützt sind.

## AML-/TF-Storylines (Demo)
- **Aid-Corridor (TF)**: NGO-ähnliche Kleinspenden (250–5.200 EUR) Richtung Konfliktregion (SY/IR/AF/UA) in 3h-Fenstern. Die Regel `TF_AID_CORRIDOR_STORY` kombiniert Purpose-Muster („Aid“, „Corridor“, „Relief“) mit Länderkorridor und Frequenz.
- **Structuring & Cash-Intensität (AML)**: Mehrere Bargeldeinzahlungen <9.500 EUR in 30 Minuten plus 6h Cash-Intensitäts-Check (>=20k) greifen auf die persistierte Historie zurück und schlagen bei wiederholtem Verhalten alarm.
- **Offshore-Hopping (Tax)**: Wiederholte Transfers >=7k in verschiedene Niedrigsteuer-Jurisdiktionen binnen 6h triggern das Tax-Profil.

## Nächste Schritte
- Dotnet-/WPF-Solution aufsetzen (wenn Zielsystem verfügbar ist) und Python-Prototyp-Logik in C# übertragen.
- Konfigurationstabellen für Risk Indicators/Axiome anlegen (Seeding via EF Core).
- Mock-Stream oder File-Watcher für Transaktions-Ingestion implementieren.
- Erste UI-Kacheln für KPIs, Live-Tabelle und Alert-Liste binden.

## Desktop GUI (PySide6) build and run

### Security defaults (OWASP-aligned)
- Login required with bcrypt hashes, password policy (>=12 chars), lockout after repeated failures (5x/5min), and inactivity re-lock.
- RBAC roles enforced in UI and code (e.g., case close requires LEAD/ADMIN).
- Audit logging is always on (login success/failure, case status changes, notes, locks).
- Input validation/sanitizing lives in `app/core/validation.py`; UI shows generic errors to avoid leaking technical details.
- No secrets in code; set `CODEX_ADMIN_PASSWORD` via environment. Consider SQLCipher/field encryption plus NTFS hardening for the SQLite file.

1. Install dependencies inside your activated `.venv` (PowerShell):
   ```powershell
   pip install -U pip
   pip install pyside6 pyinstaller bcrypt python-dotenv
   ```
2. Build the single-file GUI executable:
   ```powershell
   pyinstaller FMR_TaskForce_GUI.spec
   ```
   The build bundles `config/indicators.json` and `config/thresholds.json` and excludes web server components.
3. Launch on Windows (double-click or via shell):
   ```powershell
   .\start.bat
   ```
4. First-run admin bootstrap:
   - Provide `CODEX_ADMIN_PASSWORD` in the environment to set the initial admin password securely.
   - If absent, a random admin password is generated at startup and printed to the console; store it securely.
5. UI workflow:
   - Login dialog gates access (RBAC roles: ANALYST, LEAD, ADMIN).
   - Dashboard, Alerts, Cases, Customers, Audit, and Settings tabs are available once authenticated.
   - Inactivity auto-lock defaults to 15 minutes; use the login dialog to unlock.
6. Packaging note:
   - The GUI runs offline and does not start any FastAPI/Uvicorn server.
   - For troubleshooting, keep the console window (PyInstaller `console=True`) to view errors instead of silent exits.

### Compliance & Privacy
- See `SECURITY.md` for OWASP-aligned practices and `SECURITY_TODO.md` for the open hardening backlog.
- See `docs/legal_context.md` for DSGVO/GwG/FATF pointers and expected retention/archival considerations.
- See `docs/threat_model_de.md` for das aktuelle Threat-Model (Schutzziele, Akteure, Gegenmaßnahmen).
- See `docs/backup_strategy_de.md` für eine minimale Backup-/Restore-Strategie inkl. Hash-Prüfungen.
