# -*- coding: utf-8 -*-
"""Minimal QGIS stand-in for pure-Python core tests."""
from __future__ import annotations

import sys
import types
from pathlib import Path


PLUGINS_ROOT = Path(__file__).resolve().parents[2]
if str(PLUGINS_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGINS_ROOT))


try:
    import qgis.core  # noqa: F401
except ImportError:
    qgis = types.ModuleType("qgis")
    core = types.ModuleType("qgis.core")
    gui = types.ModuleType("qgis.gui")
    pyqt = types.ModuleType("qgis.PyQt")
    pyqt_core = types.ModuleType("qgis.PyQt.QtCore")
    pyqt_gui = types.ModuleType("qgis.PyQt.QtGui")
    pyqt_widgets = types.ModuleType("qgis.PyQt.QtWidgets")

    class QgsSettings:
        _values: dict[str, object] = {}

        def value(self, key: str, default=None):
            return self._values.get(key, default)

        def setValue(self, key: str, value) -> None:  # noqa: N802
            self._values[key] = value

    class Qt:
        class AlignmentFlag:
            AlignCenter = 1

    class QIcon:
        def __init__(self, *args, **kwargs):
            pass

    class QAction:
        def __init__(self, *args, **kwargs):
            pass

    class QToolBar:
        def __init__(self, *args, **kwargs):
            pass

    class QMessageBox:
        pass

    core.QgsSettings = QgsSettings
    pyqt_core.Qt = Qt
    pyqt_gui.QIcon = QIcon
    pyqt_gui.QAction = QAction
    pyqt_widgets.QAction = QAction
    pyqt_widgets.QToolBar = QToolBar
    pyqt_widgets.QMessageBox = QMessageBox

    qgis.core = core
    qgis.gui = gui
    qgis.PyQt = pyqt
    pyqt.QtCore = pyqt_core
    pyqt.QtGui = pyqt_gui
    pyqt.QtWidgets = pyqt_widgets

    sys.modules["qgis"] = qgis
    sys.modules["qgis.core"] = core
    sys.modules["qgis.gui"] = gui
    sys.modules["qgis.PyQt"] = pyqt
    sys.modules["qgis.PyQt.QtCore"] = pyqt_core
    sys.modules["qgis.PyQt.QtGui"] = pyqt_gui
    sys.modules["qgis.PyQt.QtWidgets"] = pyqt_widgets
