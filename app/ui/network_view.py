from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

try:
    from PySide6 import QtSvg
except Exception:  # noqa: BLE001
    QtSvg = None

from app.storage.db import Database


class NetworkView(QtWidgets.QGraphicsView):
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.setScene(QtWidgets.QGraphicsScene(self))
        self.setRenderHint(QtGui.QPainter.Antialiasing)
        self.max_rows = 200
        self.focus_key: str | None = None
        self.refresh()

    def refresh(self) -> None:
        scene = self.scene()
        scene.clear()
        txs = self.db.list_transactions(limit=self.max_rows)
        if self.focus_key:
            txs = [tx for tx in txs if self.focus_key in (tx.account_id, tx.counterparty_country)]
        node_map: dict[str, tuple[QtWidgets.QGraphicsEllipseItem, float, float]] = {}
        adjacency: dict[str, set[str]] = {}
        edge_weights: list[tuple[str, str, float]] = []
        max_amount = max((abs(tx.amount) for tx in txs), default=1.0)

        def add_node(key: str, label: str, color: QtGui.QColor, cluster: int):
            if key in node_map:
                return node_map[key]
            pos_x = 120 * (cluster % 5) + (len(node_map) % 5) * 40
            pos_y = 60 * (cluster // 5) + (len(node_map) // 5) * 20
            size = 40
            ellipse = scene.addEllipse(pos_x, pos_y, size, size, brush=QtGui.QBrush(color))
            text = scene.addText(label)
            text.setDefaultTextColor(QtGui.QColor("#e5e7eb"))
            text.setPos(pos_x + 4, pos_y + 10)
            node_map[key] = (ellipse, pos_x + size / 2, pos_y + size / 2)
            return node_map[key]

        cluster_color = ["#3b82f6", "#22d3ee", "#f59e0b", "#ef4444", "#10b981", "#a855f7"]
        account_clusters: dict[str, int] = {}

        for idx, tx in enumerate(txs):
            account_key = f"acct:{tx.account_id}"
            country_key = f"country:{tx.counterparty_country}"
            cluster = account_clusters.setdefault(tx.account_id, idx % len(cluster_color))
            acct_node = add_node(account_key, tx.account_id[-6:], QtGui.QColor(cluster_color[cluster]), cluster)
            country_node = add_node(country_key, tx.counterparty_country, QtGui.QColor("#94a3b8"), cluster)
            adjacency.setdefault(account_key, set()).add(country_key)
            adjacency.setdefault(country_key, set()).add(account_key)
            edge_weights.append((account_key, country_key, abs(tx.amount)))
            width = max(1.5, 4.0 * abs(tx.amount) / max_amount)
            line = scene.addLine(
                acct_node[1],
                acct_node[2],
                country_node[1],
                country_node[2],
                QtGui.QPen(QtGui.QColor("#f8fafc"), width),
            )
            line.setToolTip(f"Amount {tx.amount:.2f} {tx.currency}")

        cluster_count = len({v for v in account_clusters.values()}) or 1
        correlation_total = 0
        confidence_sum = 0.0
        reason_tokens: dict[str, int] = {}
        alerts = list(self.db.list_alerts(limit=80))
        correlation_rows = self.db.correlation_metrics([row["id"] for row in alerts], max_rows=400)
        correlation_total = len(correlation_rows)
        for row in correlation_rows:
            if "confidence" in row.keys() and row["confidence"]:
                confidence_sum += row["confidence"]
            if "reason_token" in row.keys() and row["reason_token"]:
                reason_tokens[row["reason_token"]] = reason_tokens.get(row["reason_token"], 0) + 1
        avg_conf = (confidence_sum / correlation_total) if correlation_total else 0
        summary = scene.addText(
            f"Clusters: {cluster_count} | edges: {len(edge_weights)} | correlations: {correlation_total} | avg confidence {avg_conf:.2f}"
        )
        summary.setPos(20, scene.itemsBoundingRect().height() + 20)
        token_text = scene.addText("Tokens: " + ", ".join(f"{k}:{v}" for k, v in reason_tokens.items()))
        token_text.setPos(20, summary.pos().y() + 20)
        scene.setSceneRect(scene.itemsBoundingRect())

    def export_png(self, path: str) -> None:
        target = QtCore.QRectF(self.scene().itemsBoundingRect())
        image = QtGui.QImage(target.size().toSize(), QtGui.QImage.Format_ARGB32)
        image.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(image)
        self.scene().render(painter)
        painter.end()
        image.save(path)

    def export_svg(self, path: str) -> None:
        if not QtSvg:
            raise RuntimeError("QtSvg not available for SVG export")
        generator = QtSvg.QSvgGenerator()
        generator.setFileName(path)
        target = self.scene().itemsBoundingRect()
        generator.setSize(QtCore.QSize(int(target.width()), int(target.height())))
        painter = QtGui.QPainter(generator)
        self.scene().render(painter)
        painter.end()

    def set_focus(self, focus: str | None) -> None:
        self.focus_key = focus or None
        self.refresh()
