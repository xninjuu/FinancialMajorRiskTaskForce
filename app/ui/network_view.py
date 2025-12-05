from __future__ import annotations

from PySide6 import QtGui, QtWidgets

from app.storage.db import Database


class NetworkView(QtWidgets.QGraphicsView):
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.setScene(QtWidgets.QGraphicsScene(self))
        self.setRenderHint(QtGui.QPainter.Antialiasing)
        self.refresh()

    def refresh(self) -> None:
        scene = self.scene()
        scene.clear()
        txs = self.db.list_transactions(limit=120)
        x_offset = 50
        y_offset = 50
        node_map = {}

        def add_node(key: str, label: str, color: QtGui.QColor, pos_x: int, pos_y: int):
            if key in node_map:
                return node_map[key]
            ellipse = scene.addEllipse(pos_x, pos_y, 80, 40, brush=QtGui.QBrush(color))
            text = scene.addText(label)
            text.setPos(pos_x + 5, pos_y + 10)
            node_map[key] = (ellipse, pos_x + 40, pos_y + 20)
            return node_map[key]

        row = 0
        for tx in txs:
            account_key = f"acct:{tx.account_id}"
            country_key = f"country:{tx.counterparty_country}"
            acct_node = add_node(account_key, tx.account_id[-6:], QtGui.QColor("#e74c3c"), x_offset, y_offset + row * 80)
            country_node = add_node(country_key, tx.counterparty_country, QtGui.QColor("#2c3e50"), x_offset + 220, y_offset + row * 80)
            scene.addLine(acct_node[1], acct_node[2], country_node[1], country_node[2], QtGui.QPen(QtGui.QColor("#bdc3c7"), 2))
            row = (row + 1) % 6
            if row == 0:
                y_offset += 20
        scene.setSceneRect(scene.itemsBoundingRect())
