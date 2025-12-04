from __future__ import annotations

import base64
import hashlib
import json
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from .persistence import PersistenceLayer


HTML_HEAD = """
<!doctype html>
<html lang=\"de\">
<head>
  <meta charset=\"utf-8\" />
  <title>FMR TaskForce Alerts</title>
  <style>
    body { font-family: Segoe UI, Roboto, sans-serif; background:#0e0e10; color:#f5f5f7; margin:0; padding:20px; }
    h1 { color:#e50914; }
    .card { background:#16161a; border-radius:10px; padding:16px; margin-bottom:12px; box-shadow: 0 10px 30px rgba(0,0,0,0.35); }
    .pill { display:inline-block; padding:4px 8px; border-radius:999px; font-size:12px; margin-right:8px; }
    .pill.high { background:#f05454; color:#fff; }
    .pill.medium { background:#f2a007; color:#0e0e10; }
    .pill.low { background:#0fbf61; color:#0e0e10; }
    .muted { color:#9ea0a6; font-size:13px; }
    .stack { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
  </style>
</head>
<body>
<h1>Realtime Alerts (read-only)</h1>
"""

HTML_FOOT = "</body></html>"


class DashboardHandler(BaseHTTPRequestHandler):
    persistence: PersistenceLayer | None = None
    user: str = "analyst"
    password: str = "analyst"
    password_hash: str | None = None

    def _write(self, status: int, content: str) -> None:
        body = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _unauthorized(self) -> None:
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="codex"')
        self.end_headers()

    def _require_auth(self) -> bool:
        header = self.headers.get("Authorization")
        if not header or not header.startswith("Basic "):
            self._unauthorized()
            return False
        encoded = header.split(" ", 1)[1]
        try:
            decoded = base64.b64decode(encoded).decode("utf-8")
        except Exception:
            self._unauthorized()
            return False
        username, _, password = decoded.partition(":")
        if username != self.user:
            self._unauthorized()
            return False
        if self.password_hash:
            computed = base64.b16encode(hashlib.sha256(password.encode("utf-8")).digest()).decode("ascii").lower()
            if computed != self.password_hash:
                self._unauthorized()
                return False
            return True
        if password != self.password:
            self._unauthorized()
            return False
        return True

    def _render_alerts(self) -> str:
        if not self.persistence:
            return "".join([HTML_HEAD, "<p>Keine Datenquelle.</p>", HTML_FOOT])
        query = parse_qs(urlparse(self.path).query)
        domain = query.get("domain", [None])[0]
        status = query.get("status", [None])[0]
        min_score = float(query.get("min_score", [0])[0]) if "min_score" in query else None
        since = None
        if "since" in query:
            try:
                since = datetime.fromisoformat(query["since"][0])
            except ValueError:
                since = None
        rows = self.persistence.list_alerts(limit=50, domain=domain, status=status, min_score=min_score, since=since)
        content = [HTML_HEAD]
        content.append("<p class='muted'>Filter: domain, status, min_score, since=ISO8601</p>")
        for row in rows:
            risk_level = row["risk_level"].lower()
            pill_class = "high" if risk_level == "high" else "medium" if risk_level == "medium" else "low"
            rationales = json.loads(row["rationales"] or "[]")
            hits = [r for r in rationales if r.get("is_hit")][:2]
            rationale_text = "; ".join([
                f"{h.get('code')} ({h.get('explanation') or h.get('description')})" for h in hits
            ])
            content.append(
                f"<div class='card'>"
                f"<div class='stack'><span class='pill {pill_class}'>{row['risk_level']}</span>"
                f"<strong>{row['id']}</strong> – Score {row['score']:.1f}</div>"
                f"<div class='muted'>TX {row['transaction_id']} | Case {row['case_id'] or 'n/a'} | {row['created_at']}</div>"
                f"<div>{rationale_text or 'Keine Treffer gespeichert'}</div>"
                f"</div>"
            )
        if not rows:
            content.append("<p class='card'>Keine Alerts vorhanden.</p>")
        content.append(HTML_FOOT)
        return "".join(content)

    def _render_cases(self) -> str:
        if not self.persistence:
            return "".join([HTML_HEAD, "<p>Keine Datenquelle.</p>", HTML_FOOT])
        query = parse_qs(urlparse(self.path).query)
        status = query.get("status", [None])[0]
        rows = self.persistence.list_cases(status=status)
        content = [HTML_HEAD.replace("Realtime Alerts", "Cases")]
        for row in rows:
            case_id = row["id"]
            notes = self.persistence.case_notes(case_id)
            alerts = self.persistence.alerts_for_case(case_id)
            content.append(
                f"<div class='card'><div class='stack'><span class='pill medium'>{row['status']}</span>"
                f"<strong>{case_id}</strong> – Priority {row['priority'] or 'Normal'}</div>"
                f"<div class='muted'>Created {row['created_at']} | Updated {row['updated_at']} | Label {row['label'] or 'n/a'}</div>"
                f"<div class='muted'>Alerts: {len(alerts)}</div>"
            )
            if alerts:
                content.append("<ul>")
                for alert in alerts:
                    content.append(
                        f"<li>{alert['id']} – Score {alert['score']:.1f} – {alert['risk_level']} ({alert['domain']})</li>"
                    )
                content.append("</ul>")
            if notes:
                content.append("<div class='muted'>Notes:</div><ul>")
                for note in notes:
                    content.append(
                        f"<li>{note.created_at.isoformat()} {note.author}: {note.message}</li>"
                    )
                content.append("</ul>")
            content.append("</div>")
        if not rows:
            content.append("<p class='card'>Keine Cases vorhanden.</p>")
        content.append(HTML_FOOT)
        return "".join(content)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/health"):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
            return
        if not self._require_auth():
            return
        if self.path.startswith("/cases"):
            self._write(200, self._render_cases())
            return
        self._write(200, self._render_alerts())


class DashboardServer:
    def __init__(
        self,
        persistence: PersistenceLayer,
        host: str = "0.0.0.0",
        port: int = 8000,
        user: str = "analyst",
        password: str | None = "analyst",
        password_hash: str | None = None,
    ) -> None:
        DashboardHandler.persistence = persistence
        DashboardHandler.user = user
        DashboardHandler.password = password or ""
        DashboardHandler.password_hash = password_hash
        self.server = HTTPServer((host, port), DashboardHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.server.shutdown()
        self.thread.join()
