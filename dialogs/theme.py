"""Palette-aware styling for the 02truesize dock.

Derives every surface and text colour from the active Qt palette so the dock
stays readable under QGIS light, dark, high-contrast, and custom themes while
keeping the teal accent identity.
"""
from __future__ import annotations

from qgis.PyQt.QtGui import QColor, QPalette
from qgis.PyQt.QtWidgets import QApplication, QWidget


def _hex(color: QColor) -> str:
    return color.name(QColor.NameFormat.HexRgb)


def _mix(first: QColor, second: QColor, amount: float) -> QColor:
    amount = max(0.0, min(1.0, float(amount)))
    return QColor(
        round(first.red() * (1.0 - amount) + second.red() * amount),
        round(first.green() * (1.0 - amount) + second.green() * amount),
        round(first.blue() * (1.0 - amount) + second.blue() * amount),
    )


def _contrast_text(background: QColor) -> QColor:
    luminance = (
        0.2126 * background.red()
        + 0.7152 * background.green()
        + 0.0722 * background.blue()
    )
    return QColor("#102019") if luminance >= 150 else QColor("#FFFFFF")


def _relative_luminance(color: QColor) -> float:
    channels = []
    for value in (color.redF(), color.greenF(), color.blueF()):
        channels.append(
            value / 12.92
            if value <= 0.04045
            else ((value + 0.055) / 1.055) ** 2.4
        )
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(first: QColor, second: QColor) -> float:
    """Return the WCAG relative-luminance contrast ratio."""
    lighter, darker = sorted(
        (_relative_luminance(first), _relative_luminance(second)),
        reverse=True,
    )
    return (lighter + 0.05) / (darker + 0.05)


def dock_color_tokens(palette: QPalette | None = None) -> dict[str, str]:
    """Return the palette-derived colours used by the dock stylesheet."""
    active = palette or QApplication.palette()
    window = active.color(QPalette.ColorRole.Window)
    base = active.color(QPalette.ColorRole.Base)
    text = active.color(QPalette.ColorRole.WindowText)
    input_text = active.color(QPalette.ColorRole.Text)
    button = active.color(QPalette.ColorRole.Button)
    button_text = active.color(QPalette.ColorRole.ButtonText)
    highlight = active.color(QPalette.ColorRole.Highlight)
    disabled = active.color(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.WindowText,
    )
    dark = window.lightness() < 128

    white = QColor("#FFFFFF")
    # Teal accent — the 02truesize brand colour
    accent = QColor("#009688" if dark else "#00897b")
    accent_hover = QColor("#00B09B" if dark else "#00796b")
    accent_text = _contrast_text(accent)
    accent_soft = _mix(accent, window, 0.88 if dark else 0.92)

    surface = (
        _mix(window, white, 0.07)
        if dark
        else _mix(window, base, 0.72)
    )
    card = _mix(window, white, 0.12) if dark else base
    input_surface = _mix(base, white, 0.04) if dark else base

    border = _mix(text, surface, 0.76 if dark else 0.84)
    subtle = _mix(text, surface, 0.40 if dark else 0.37)
    hint_text = _mix(text, surface, 0.30 if dark else 0.25)

    tab_bg = _mix(surface, accent, 0.88 if dark else 0.92)
    tab_selected_bg = accent
    tab_selected_text = accent_text

    status_bg = _mix(surface, accent, 0.13 if dark else 0.06)

    if contrast_ratio(input_text, input_surface) < 4.5:
        input_text = QColor(text)
    if contrast_ratio(button_text, button) < 4.5:
        button_text = QColor(text)
    selection = highlight if highlight.isValid() else accent

    return {
        "surface": _hex(surface),
        "card": _hex(card),
        "input_surface": _hex(input_surface),
        "text": _hex(text),
        "input_text": _hex(input_text),
        "button": _hex(button),
        "button_text": _hex(button_text),
        "border": _hex(border),
        "subtle": _hex(subtle),
        "hint_text": _hex(hint_text),
        "disabled": _hex(disabled),
        "accent": _hex(accent),
        "accent_hover": _hex(accent_hover),
        "accent_text": _hex(accent_text),
        "accent_soft": _hex(accent_soft),
        "tab_bg": _hex(tab_bg),
        "tab_selected_bg": _hex(tab_selected_bg),
        "tab_selected_text": _hex(tab_selected_text),
        "status_bg": _hex(status_bg),
        "selection": _hex(selection),
    }


_TOOL_ACCENT_COLORS = {
    "truesize":    "#00897b",
    "antipode":    "#3949ab",
    "greatcircle": "#1565c0",
    "fundist":     "#2e7d32",
    "funarea":     "#2e7d32",
}


def card_accent(key: str, dark: bool) -> str:
    """Return the per-tool card accent colour, adjusted for theme."""
    light_map = _TOOL_ACCENT_COLORS
    dark_map = {
        "truesize":    "#4DB6AC",
        "antipode":    "#7986CB",
        "greatcircle": "#64B5F6",
        "fundist":     "#81C784",
        "funarea":     "#81C784",
    }
    return dark_map.get(key, light_map.get(key, "#00897b")) if dark else light_map.get(key, _TOOL_ACCENT_COLORS["truesize"])


def dock_stylesheet(palette: QPalette | None = None) -> str:
    """Build the full dock stylesheet from the current application palette."""
    t = dock_color_tokens(palette)
    return """
QWidget#z2tsRoot {
    background: %(surface)s;
    color: %(text)s;
}
QWidget#z2tsRoot QLabel {
    background: transparent;
    color: %(text)s;
}
QTabWidget::pane {
    border: none;
    background: %(surface)s;
}
QTabBar::tab {
    background: %(tab_bg)s;
    color: %(subtle)s;
    padding: 5px 9px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background: %(accent)s;
    color: %(accent_text)s;
}
QTabBar::tab:hover {
    color: %(accent)s;
}
QGroupBox {
    background: %(card)s;
    border: 1px solid %(border)s;
    border-radius: 8px;
    margin-top: 10px;
    padding: 10px 6px 6px 6px;
    font-weight: bold;
    color: %(text)s;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}
QPushButton {
    background: %(card)s;
    border: 1px solid %(border)s;
    border-radius: 6px;
    padding: 5px 10px;
    color: %(text)s;
}
QPushButton:hover {
    background: %(accent_soft)s;
    border-color: %(accent)s;
}
QPushButton:checked {
    background: %(accent)s;
    border-color: %(accent_hover)s;
    color: %(accent_text)s;
    font-weight: bold;
}
QPushButton:disabled {
    color: %(disabled)s;
    background: %(input_surface)s;
}
QPushButton[class="tool"] {
    text-align: left;
    padding: 8px 12px;
}
QPushButton[class="primary"] {
    background: %(accent)s;
    border-color: %(accent_hover)s;
    color: %(accent_text)s;
    font-weight: bold;
    padding: 10px 16px;
    font-size: 11pt;
}
QPushButton[class="primary"]:hover {
    background: %(accent_hover)s;
}
QPushButton[class="primary-drag"] {
    background: %(accent)s;
    border-color: %(accent_hover)s;
    color: %(accent_text)s;
    font-weight: bold;
    padding: 14px 18px;
    font-size: 13pt;
    border-radius: 10px;
}
QPushButton[class="primary-drag"]:hover {
    background: %(accent_hover)s;
}
QComboBox {
    background: %(input_surface)s;
    border: 1px solid %(border)s;
    border-radius: 5px;
    padding: 3px 8px;
    color: %(input_text)s;
}
QComboBox QAbstractItemView {
    background: %(card)s;
    color: %(text)s;
    selection-background-color: %(accent_soft)s;
    selection-color: %(text)s;
}
QListWidget {
    background: %(card)s;
    border: 1px solid %(border)s;
    border-radius: 6px;
    color: %(text)s;
}
QListWidget::item {
    padding: 3px 4px;
}
QListWidget::item:selected {
    background: %(accent_soft)s;
    color: %(text)s;
}
QCheckBox {
    color: %(text)s;
    background: transparent;
}
QScrollArea, QScrollArea > QWidget > QWidget {
    background: transparent;
    border: none;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: %(border)s;
    border-radius: 4px;
    min-height: 28px;
}
QScrollBar::handle:vertical:hover {
    background: %(accent)s;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QToolTip {
    background: %(card)s;
    color: %(text)s;
    border: 1px solid %(border)s;
    padding: 4px;
}
""" % t


def apply_adaptive_theme(widget: QWidget) -> None:
    """Apply the active QGIS/Qt palette without overriding font preferences."""
    widget.setStyleSheet(dock_stylesheet(widget.palette()))
