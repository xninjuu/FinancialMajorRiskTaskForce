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

## Nächste Schritte
- Solution-Skelett erzeugen (`dotnet new wpf`), Layer-Struktur und Projekte aufsetzen.
- Konfigurationstabellen für Risk Indicators/Axiome anlegen (Seeding via EF Core).
- Mock-Stream oder File-Watcher für Transaktions-Ingestion implementieren.
- Erste UI-Kacheln für KPIs, Live-Tabelle und Alert-Liste binden.
