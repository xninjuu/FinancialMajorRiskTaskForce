from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Tuple

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

    def _write(self, status: int, content: str) -> None:
        body = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _render_alerts(self) -> str:
        rows = [] if not self.persistence else self.persistence.list_alerts(limit=50)
        content = [HTML_HEAD]
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
        rows = [] if not self.persistence else self.persistence.list_cases()
        content = [HTML_HEAD.replace("Realtime Alerts", "Cases")]
        for row in rows:
            content.append(
                f"<div class='card'><div class='stack'><span class='pill medium'>{row['status']}</span>"
                f"<strong>{row['id']}</strong></div>"
                f"<div class='muted'>Created {row['created_at']} | Updated {row['updated_at']}</div>"
                f"</div>"
            )
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
        if self.path.startswith("/cases"):
            self._write(200, self._render_cases())
            return
        self._write(200, self._render_alerts())


class DashboardServer:
    def __init__(self, persistence: PersistenceLayer, host: str = "0.0.0.0", port: int = 8000) -> None:
        DashboardHandler.persistence = persistence
        self.server = HTTPServer((host, port), DashboardHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.server.shutdown()
        self.thread.join()
