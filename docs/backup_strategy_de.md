# Backup-Strategie (DE)

Diese Richtlinie beschreibt eine minimale Backup- und Restore-Strategie für die lokale SQLite-Datenbank der FMR TaskForce Desktop-App.

## Ziele
- Verlust von Ermittlungsdaten (Alerts, Cases, Audit-Logs) vermeiden.
- Integrität und Nachvollziehbarkeit nach einem Vorfall sicherstellen.
- Backups so ablegen, dass ein Dieb der Arbeitsstation nicht unmittelbar Zugriff erhält.

## Empfehlungen
1. **Pfad & Rechte**
   - DB-Datei in ein NTFS-Verzeichnis legen, das nur der aktuelle Windows-Benutzer lesen darf.
   - Keine Freigaben/Netzlaufwerke für die Live-DB verwenden.

2. **Backup-Frequenz**
   - Mindestens täglich ein verschlüsseltes Backup (z. B. ZIP mit AES) erstellen.
   - Rotationsschema (z. B. 7 Tage täglich, 4 Wochen wöchentlich) definieren.

3. **Schlüsselhandhabung**
   - Backup-Passwörter/Keys nicht im Quellcode oder in Klartext-Dateien speichern.
   - Nutzung eines Passwortmanagers oder Windows Credential Manager wird empfohlen.

4. **Speicherort**
   - Backups getrennt von der Live-DB speichern (anderes Laufwerk oder geschützter Ordner).
   - Optional: Offline-Medium (verschlüsselte USB) für langfristige Ablage.

5. **Restore-Tests**
   - Monatlich ein Restore in eine Testumgebung durchführen:
     - Kopie des Backups entpacken/entschlüsseln
     - Anwendung mit der wiederhergestellten DB starten
     - Stichproben von Cases/Alerts/Audit-Einträgen prüfen

6. **Integritätsprüfungen**
   - Hash (SHA-256) der Backup-Datei speichern und bei Restore vergleichen.
   - Optional: HMAC über die Backup-Datei mit separatem Schlüssel.

7. **Aufbewahrung & Löschung**
   - Aufbewahrungsdauer entsprechend interner Richtlinien/gesetzlicher Vorgaben (z. B. 90 Tage) festlegen.
   - Automatisierte Löschung/Archivierung alter Backups einplanen.

## Minimaler Ablauf (Beispiel)
- Script (PowerShell) erstellt täglich ein verschlüsseltes ZIP der `fmr_taskforce.db` in einen geschützten Ordner.
- Hash der ZIP-Datei wird in einer separaten Textdatei abgelegt.
- Monatlicher Restore-Test prüft Öffnen der App mit dem Backup.
