# -*- coding: utf-8 -*-
"""02truesize - Map Truth Lab: main plugin class.

Toolbar toggle + dock; map tools are created lazily and routed into the
dock's result panels. No top-level QGIS menu (02-family convention).
"""
from __future__ import annotations

import os
from contextlib import suppress

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QMessageBox, QToolBar

try:  # Qt5: QtWidgets / Qt6: QtGui
    from qgis.PyQt.QtWidgets import QAction
except ImportError:  # pragma: no cover - QGIS 4 / Qt6
    from qgis.PyQt.QtGui import QAction

PLUGIN_TITLE = "02truesize — Map Truth Lab"


class O2TrueSizePlugin:
    TOOLBAR_NAME = "02truesize Toolbar"

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.icon_dir = os.path.join(self.plugin_dir, "icons")
        self.actions: list[QAction] = []
        self.toolbar: QToolBar | None = None
        self._dock = None
        self._tools: dict[str, object] = {}
        self._map_tool_hooked = False

    # ── QGIS lifecycle ────────────────────────────────────────────────

    def initGui(self) -> None:  # noqa: N802 (QGIS API)
        self.toolbar = QToolBar(self.TOOLBAR_NAME)
        self.toolbar.setObjectName("O2TrueSizeToolbar")
        self.iface.addToolBar(self.toolbar)
        self.panel_action = self._add_action(
            os.path.join(self.icon_dir, "icon.png"),
            PLUGIN_TITLE,
            self._toggle_dock,
            checkable=True,
            status_tip="Open or close the 02truesize Map Truth Lab",
        )

    def unload(self) -> None:
        canvas = self.iface.mapCanvas()
        with suppress(TypeError, RuntimeError):
            canvas.mapToolSet.disconnect(self._on_map_tool_set)
        current = canvas.mapTool()
        if current is not None and current in self._tools.values():
            canvas.unsetMapTool(current)
        for tool in self._tools.values():
            dispose = getattr(tool, "dispose", None)
            if callable(dispose):
                with suppress(Exception):
                    dispose()
        self._tools.clear()
        if self._dock is not None:
            with suppress(Exception):
                self._dock.dispose()
            self.iface.removeDockWidget(self._dock)
            self._dock.deleteLater()
            self._dock = None
        if self.toolbar is not None:
            for action in self.actions:
                self.toolbar.removeAction(action)
            self.iface.mainWindow().removeToolBar(self.toolbar)
            self.toolbar.deleteLater()
            self.toolbar = None
        self.actions.clear()

    # ── dock ──────────────────────────────────────────────────────────

    def _toggle_dock(self) -> None:
        if self._dock is None:
            try:
                from .dialogs.dock import TrueSizeDockWidget

                self._dock = TrueSizeDockWidget(self.iface, self.iface.mainWindow())
                self._dock.setObjectName("O2TrueSizeDock")
                self._dock.visibilityChanged.connect(self.panel_action.setChecked)
                self._dock.request_tool.connect(self._activate_tool)
                self._dock.request_deactivate.connect(self._deactivate_tool)
                self.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._dock)
                if not self._map_tool_hooked:
                    self.iface.mapCanvas().mapToolSet.connect(self._on_map_tool_set)
                    self._map_tool_hooked = True
            except Exception as exc:
                QMessageBox.critical(self.iface.mainWindow(), PLUGIN_TITLE,
                                     f"Could not create the panel:\n{exc}")
                self.panel_action.setChecked(False)
                return
        self._dock.setVisible(not self._dock.isVisible())
        if self._dock.isVisible():
            self._dock.raise_()

    # ── map tools ─────────────────────────────────────────────────────

    def _activate_tool(self, key: str) -> None:
        canvas = self.iface.mapCanvas()
        tool = self._tools.get(key)
        if tool is None:
            tool = self._create_tool(key)
            if tool is None:
                self._dock.show_message(key, f"Could not create the '{key}' tool.")
                return
            self._tools[key] = tool
        canvas.setMapTool(tool)

    def _deactivate_tool(self) -> None:
        canvas = self.iface.mapCanvas()
        current = canvas.mapTool()
        if current is not None and current in self._tools.values():
            canvas.unsetMapTool(current)

    def _create_tool(self, key: str):
        canvas = self.iface.mapCanvas()
        dock = self._dock
        if key == "truesize":
            from .tools.truesize import TrueSizePickTool

            tool = TrueSizePickTool(canvas, dock.manager, dock.world,
                                    dock.truesize_source_mode, self.iface.activeLayer)
            tool.message.connect(dock.set_tool_message)
            return tool
        if key == "antipode":
            from .tools.antipode import AntipodeTool

            tool = AntipodeTool(canvas, dock.world)
            tool.result.connect(dock.show_antipode)
            tool.message.connect(lambda text: dock.show_message("antipode", text))
            return tool
        if key == "greatcircle":
            from .tools.greatcircle import GreatCircleTool

            tool = GreatCircleTool(canvas)
            tool.result.connect(dock.show_greatcircle)
            tool.message.connect(lambda text: dock.show_message("greatcircle", text))
            return tool
        if key == "fundist":
            from .tools.funmeasure import FunnyDistanceTool

            tool = FunnyDistanceTool(canvas)
            tool.result.connect(dock.show_funits)
            tool.message.connect(lambda text: dock.show_message("fundist", text))
            return tool
        if key == "funarea":
            from .tools.funmeasure import FunnyAreaTool

            tool = FunnyAreaTool(canvas)
            tool.result.connect(dock.show_funits)
            tool.message.connect(lambda text: dock.show_message("funarea", text))
            return tool
        return None

    def _on_map_tool_set(self, new_tool, old_tool) -> None:
        del old_tool
        if self._dock is not None and new_tool not in self._tools.values():
            self._dock.uncheck_all_tools()

    # ── helpers ───────────────────────────────────────────────────────

    def _add_action(self, icon_path, text, callback, *, checkable=False,
                    status_tip=None) -> QAction:
        action = QAction(QIcon(icon_path), text, self.iface.mainWindow())
        action.triggered.connect(callback)
        action.setCheckable(checkable)
        if status_tip:
            action.setStatusTip(status_tip)
        if self.toolbar is not None:
            self.toolbar.addAction(action)
        self.actions.append(action)
        return action
