# Threat Model (DE)

Dieses Dokument beschreibt ein Basis-Threat-Model für die FMR TaskForce Desktop-Applikation.
Es fokussiert auf ein Einzelplatz-Setup (Windows, PySide6, SQLite) ohne Netzwerkpflicht.

## 1. Schutzziele
- **Vertraulichkeit**: Ermittlungs- und Kundendaten dürfen nicht von Unbefugten gelesen werden.
- **Integrität**: Alerts, Cases, Audit-Logs dürfen nicht unbemerkt manipuliert werden.
- **Verfügbarkeit**: Das Tool soll im Offline-Betrieb nutzbar bleiben.
- **Nachvollziehbarkeit**: Aktionen müssen auditierbar bleiben (wer, wann, was, auf welchem Objekt).

## 2. Bedrohungsakteure
- Interne Nutzer mit zu weitreichenden Rechten (Insider Threat).
- Externe Angreifer mit physischem Zugang zum Rechner (gestohlener Laptop, Offline-Angriff).
- Malware/Ransomware auf dem Host-System.
- Fehlkonfiguration (z. B. schwache Passwörter, deaktivierte Sperren).

## 3. Angriffsvektoren & Gegenmaßnahmen
- **Unbefugter Zugang zur App**
  - Gegenmaßnahme: Login mit bcrypt-Hash, Lockout, Rollenmodell, Inaktivitäts-Lock.
- **Datenexfiltration über DB-Datei**
  - Gegenmaßnahme: DB im geschützten NTFS-Pfad, optionale Verschlüsselung/Backups, Minimierung von PII.
- **Manipulation von Cases/Audit**
  - Gegenmaßnahme: Pflicht-Audit-Log, beschränkte Rollen (LEAD/ADMIN), Validierung/Whitelists.
- **Malware/Tampering der EXE**
  - Gegenmaßnahme: Code-Signing (empfohlen), Hash-Prüfung der EXE vor Start, sichere Bezugsquelle.
- **Schwache Konfiguration/Secrets im Klartext**
  - Gegenmaßnahme: .env/OS-Secret-Store, Passwort-Policy (>=12 Zeichen), keine Hardcoded-Secrets.

## 4. Annahmen & Rest-Risiko
- Einzelplatzbetrieb auf gehärtetem Windows-Account (BitLocker, regelmäßige Updates).
- Wer physischen Vollzugriff auf das System hat, kann mit genügend Aufwand Daten extrahieren.
- EXE-Signierung und Hash-Veröffentlichung reduzieren Manipulationsrisiko, ersetzen aber keine Betriebshygiene.

## 5. Prüf- und Härtungsmaßnahmen (Auszug)
- Passwort-Policy erzwingen, Lockout aktiv, Session-Lock <= 15 Minuten.
- Audit-Log für Login, Case-Status, Notizen, Settings-Änderungen.
- Validierung aller UI-Eingaben über zentrale Helper (`app/core/validation.py`).
- Optional: Integritäts-Hash der EXE prüfen, bevor die App startet.
- Backups verschlüsselt ablegen und Restore testen (siehe `docs/backup_strategy_de.md`).
