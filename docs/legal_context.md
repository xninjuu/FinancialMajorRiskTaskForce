# Rechtlicher Kontext (Kurzüberblick)

- **DSGVO (Art. 5, 25)**: Datenschutz durch Technikgestaltung, Datenminimierung und Zweckbindung. Loggen nur, was für Financial-Crime-Use-Cases nötig ist; sensible Freitexte vermeiden.
- **GwG / BaFin-AuA**: Risikobasierter Ansatz, dokumentierte Monitoring-Prozesse, Nachvollziehbarkeit von Alerts/Cases und deren Bearbeitung.
- **FATF Risk-Based Approach**: Geografie-, Produkt- und Verhaltensrisiken fließen in die Indikatorik und Score-Zerlegung ein; Audit-Logs sichern die Nachvollziehbarkeit.
- **Aufbewahrung & Löschung**: Für ein Produktiv-Setup sollten Retention-Policies konfigurierbar sein (Cases, Audit-Logs, Transaktionshistorie) und regelmäßig überprüft werden.
- **Einsatzkontext**: Einzelplatz-/Desktop-Tool, kein Offloading in fremde Cloud-Dienste; Netzwerkzugriffe sind standardmäßig deaktiviert.
