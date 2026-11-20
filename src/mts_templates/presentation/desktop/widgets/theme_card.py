"""Карточка выбора темы: миниатюра интерфейса, название и радиокнопка."""

from __future__ import annotations

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QEvent,
    QPointF,
    QPropertyAnimation,
    QRectF,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QEnterEvent,
    QFont,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import QWidget

from mts_templates.presentation.desktop.theme_catalog import Theme

CARD_WIDTH = 224
CARD_HEIGHT = 176
PREVIEW_MARGIN = 10
PREVIEW_HEIGHT = 126


class ThemeCard(QWidget):
    """Показывает миниатюру темы; клик выбирает её."""

    clicked = Signal(str)

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._selected = False
        self._hover = 0.0

        self._animation = QPropertyAnimation(self, b"hover_progress", self)
        self._animation.setDuration(140)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(theme.name)
        self.setToolTip(f"{theme.name}\n{theme.description}")

    @property
    def theme_id(self) -> str:
        return self._theme.id

    def set_selected(self, selected: bool) -> None:
        if selected == self._selected:
            return
        self._selected = selected
        self.update()

    def _get_hover(self) -> float:
        return self._hover

    def _set_hover(self, value: float) -> None:
        self._hover = value
        self.update()

    hover_progress = Property(float, _get_hover, _set_hover)

    def enterEvent(self, event: QEnterEvent) -> None:
        self._animate_hover(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        self._animate_hover(0.0)
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._theme.id)
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit(self._theme.id)
            return
        super().keyPressEvent(event)

    def _animate_hover(self, target: float) -> None:
        self._animation.stop()
        self._animation.setStartValue(self._hover)
        self._animation.setEndValue(target)
        self._animation.start()

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        theme = self._theme
        palette = theme.palette
        radius = theme.radius

        card = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        if theme.hard_shadow:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#111111"))
            painter.drawRoundedRect(card.translated(4.0, 4.0), radius, radius)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(palette.surface))
        painter.drawRoundedRect(card, radius, radius)

        if self._hover > 0.02 and not self._selected:
            glow = QColor(palette.accent)
            glow.setAlphaF(0.18 * self._hover)
            painter.setBrush(glow)
            painter.drawRoundedRect(card.adjusted(-2.0, -2.0, 2.0, 2.0), radius + 2, radius + 2)

        preview = QRectF(
            PREVIEW_MARGIN,
            PREVIEW_MARGIN,
            card.width() - 2 * PREVIEW_MARGIN,
            PREVIEW_HEIGHT,
        )
        self._draw_preview(painter, preview)

        name_rect = QRectF(12.0, preview.bottom() + 8.0, card.width() - 48.0, 24.0)
        name_font = QFont(self.font())
        name_font.setPointSize(10)
        name_font.setBold(True)
        painter.setFont(name_font)
        painter.setPen(QColor(palette.text))
        painter.drawText(
            name_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            theme.name,
        )

        self._draw_radio(
            painter,
            QPointF(card.right() - 18.0, preview.bottom() + 20.0),
            radius=9.0,
        )

        if self._selected:
            border_color = QColor(palette.accent)
            border_width = 3.0
        elif self._hover > 0.02:
            border_color = QColor(palette.accent)
            border_color.setAlphaF(min(1.0, 0.45 + 0.55 * self._hover))
            border_width = 1.0 + 1.5 * self._hover
        else:
            border_color = QColor(palette.border)
            border_width = float(theme.border_width)
        pen = QPen(border_color)
        pen.setWidthF(border_width)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(card, radius, radius)

        if self.hasFocus():
            focus = QPen(QColor(palette.accent))
            focus.setStyle(Qt.PenStyle.DashLine)
            focus.setWidthF(1.0)
            painter.setPen(focus)
            painter.drawRoundedRect(card.adjusted(4.0, 4.0, -4.0, -4.0), radius, radius)

    def _draw_preview(self, painter: QPainter, rect: QRectF) -> None:
        theme = self._theme
        palette = theme.palette
        radius = max(2, theme.radius - 2)

        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        painter.save()
        painter.setClipPath(path)

        painter.fillRect(rect, QColor(palette.window))
        self._draw_atmosphere(painter, rect)

        sidebar_width = 26.0
        top_height = 12.0
        painter.fillRect(
            QRectF(rect.x(), rect.y(), sidebar_width, rect.height()),
            QColor(palette.surface_alt),
        )
        painter.fillRect(
            QRectF(rect.x() + sidebar_width, rect.y(), rect.width() - sidebar_width, top_height),
            QColor(palette.header),
        )

        content_left = rect.x() + sidebar_width + 6.0
        content_width = rect.right() - content_left - 6.0
        card_top = rect.y() + top_height + 6.0
        card_height = 30.0
        left_width = content_width * 0.52
        self._mini_card(
            painter,
            QRectF(content_left, card_top, left_width, card_height),
            palette.surface,
            palette.border,
            radius,
        )
        self._mini_card(
            painter,
            QRectF(
                content_left + left_width + 5.0,
                card_top,
                content_width - left_width - 5.0,
                card_height,
            ),
            palette.surface,
            palette.border,
            radius,
        )
        line_y = card_top + card_height + 6.0
        painter.fillRect(
            QRectF(content_left, line_y, content_width * 0.82, 4.0), QColor(palette.text_muted)
        )
        painter.fillRect(
            QRectF(content_left, line_y + 8.0, content_width * 0.62, 4.0),
            QColor(palette.border),
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(palette.accent))
        painter.drawRoundedRect(
            QRectF(content_left, rect.bottom() - 18.0, 46.0, 11.0),
            min(radius, 3),
            min(radius, 3),
        )
        painter.setBrush(QColor(palette.accent_secondary))
        painter.drawEllipse(QPointF(rect.right() - 12.0, rect.y() + 6.0), 3.0, 3.0)

        self._draw_theme_marks(painter, rect, radius)
        painter.restore()

        border = QPen(QColor(palette.border))
        border.setWidthF(float(theme.border_width))
        painter.setPen(border)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, radius, radius)

    def _mini_card(
        self,
        painter: QPainter,
        rect: QRectF,
        surface: str,
        border: str,
        radius: int,
    ) -> None:
        painter.setPen(QPen(QColor(border), 1.0))
        painter.setBrush(QColor(surface))
        painter.drawRoundedRect(rect, min(radius, 4), min(radius, 4))

    def _draw_atmosphere(self, painter: QPainter, rect: QRectF) -> None:
        """Фоновые пятна и градиенты, характерные для темы."""
        theme = self._theme
        palette = theme.palette

        if theme.id == "ethereal_mesh":
            self._orb(painter, rect, 0.22, 0.25, palette.accent, 90)
            self._orb(painter, rect, 0.78, 0.18, palette.accent_secondary, 80)
            self._orb(painter, rect, 0.62, 0.78, palette.positive, 60)
        elif theme.id == "lofi_cozy":
            gradient = QRadialGradient(
                QPointF(rect.right() - 24.0, rect.y() + 18.0),
                rect.width() * 0.75,
            )
            warm = QColor("#ffd9a0")
            warm.setAlpha(120)
            gradient.setColorAt(0.0, warm)
            transparent = QColor("#ffd9a0")
            transparent.setAlpha(0)
            gradient.setColorAt(1.0, transparent)
            painter.fillRect(rect, gradient)
            self._grain(painter, rect)
        elif theme.id == "biophilic_glasshouse":
            leaf = QColor(palette.accent_secondary)
            leaf.setAlpha(55)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(leaf)
            for cx, cy, rx, ry, angle in (
                (0.16, 0.22, 26.0, 9.0, 35.0),
                (0.86, 0.30, 22.0, 8.0, -30.0),
                (0.70, 0.82, 30.0, 10.0, 20.0),
            ):
                painter.save()
                painter.translate(rect.x() + rect.width() * cx, rect.y() + rect.height() * cy)
                painter.rotate(angle)
                painter.drawEllipse(QPointF(0.0, 0.0), rx, ry)
                painter.restore()
        elif theme.id == "cassette_futurism":
            glow = QRadialGradient(QPointF(rect.x() + 40.0, rect.y() + 34.0), 70.0)
            amber = QColor(palette.accent)
            amber.setAlpha(70)
            glow.setColorAt(0.0, amber)
            clear = QColor(palette.accent)
            clear.setAlpha(0)
            glow.setColorAt(1.0, clear)
            painter.fillRect(rect, glow)
        elif theme.id == "dark_art_deco":
            emerald = QColor(palette.accent_secondary)
            emerald.setAlpha(60)
            painter.fillRect(
                QRectF(rect.x(), rect.y(), rect.width(), rect.height() * 0.45), emerald
            )

    def _draw_theme_marks(self, painter: QPainter, rect: QRectF, radius: int) -> None:
        """Характерные детали поверх миниатюры."""
        theme = self._theme
        palette = theme.palette

        if theme.id == "neo_brutalism":
            painter.setPen(QPen(QColor("#111111"), 3.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect.adjusted(1.5, 1.5, -1.5, -1.5))
            painter.fillRect(
                QRectF(rect.right() - 34.0, rect.bottom() - 30.0, 14.0, 14.0),
                QColor(palette.accent),
            )
            painter.fillRect(
                QRectF(rect.right() - 18.0, rect.bottom() - 30.0, 10.0, 14.0),
                QColor(palette.accent_secondary),
            )
        elif theme.id == "cassette_futurism":
            scan = QColor("#000000")
            scan.setAlpha(28)
            y = rect.y()
            while y < rect.bottom():
                painter.fillRect(QRectF(rect.x(), y, rect.width(), 1.0), scan)
                y += 3.0
            painter.setPen(QColor(palette.accent_secondary))
            font = QFont("Consolas")
            font.setPointSize(7)
            painter.setFont(font)
            painter.drawText(
                QRectF(rect.x() + 32.0, rect.bottom() - 16.0, 70.0, 12.0),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                "> READY",
            )
        elif theme.id == "swiss_minimalism":
            grid = QColor(palette.border)
            grid.setAlpha(90)
            painter.setPen(QPen(grid, 1.0))
            x = rect.x()
            while x < rect.right():
                painter.drawLine(QPointF(x, rect.y()), QPointF(x, rect.bottom()))
                x += 14.0
            y = rect.y()
            while y < rect.bottom():
                painter.drawLine(QPointF(rect.x(), y), QPointF(rect.right(), y))
                y += 14.0
            painter.fillRect(
                QRectF(rect.right() - 24.0, rect.y() + 20.0, 10.0, 10.0),
                QColor(palette.accent),
            )
        elif theme.id == "dark_art_deco":
            gold = QColor(palette.accent)
            painter.setPen(QPen(gold, 1.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(5.0, 5.0, -5.0, -5.0), radius, radius)
            painter.drawArc(
                QRectF(rect.center().x() - 26.0, rect.bottom() - 46.0, 52.0, 52.0),
                0,
                180 * 16,
            )
            painter.drawLine(
                QPointF(rect.center().x() - 32.0, rect.bottom() - 12.0),
                QPointF(rect.center().x() + 32.0, rect.bottom() - 12.0),
            )
        elif theme.id == "ethereal_mesh":
            glass = QColor("#ffffff")
            glass.setAlpha(70)
            painter.setPen(QPen(QColor("#ffffff"), 1.0))
            painter.setBrush(glass)
            painter.drawRoundedRect(
                QRectF(rect.x() + 34.0, rect.y() + 20.0, rect.width() - 46.0, 38.0),
                8,
                8,
            )

    def _orb(
        self,
        painter: QPainter,
        rect: QRectF,
        cx: float,
        cy: float,
        color: str,
        alpha: int,
    ) -> None:
        center = QPointF(rect.x() + rect.width() * cx, rect.y() + rect.height() * cy)
        gradient = QRadialGradient(center, 46.0)
        inner = QColor(color)
        inner.setAlpha(alpha)
        outer = QColor(color)
        outer.setAlpha(0)
        gradient.setColorAt(0.0, inner)
        gradient.setColorAt(1.0, outer)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawEllipse(center, 46.0, 46.0)

    def _grain(self, painter: QPainter, rect: QRectF) -> None:
        seed = 20261120
        grain = QColor("#5a4432")
        grain.setAlpha(38)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(grain)
        for _ in range(90):
            seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
            x = rect.x() + (seed % max(1, int(rect.width())))
            seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
            y = rect.y() + (seed % max(1, int(rect.height())))
            painter.drawRect(QRectF(x, y, 1.0, 1.0))

    def _draw_radio(self, painter: QPainter, center: QPointF, radius: float) -> None:
        palette = self._theme.palette
        if self._selected:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(palette.accent))
            painter.drawEllipse(center, radius, radius)
            check = QPen(QColor(palette.accent_text))
            check.setWidthF(2.0)
            check.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(check)
            painter.drawLine(
                QPointF(center.x() - 4.0, center.y()),
                QPointF(center.x() - 1.0, center.y() + 3.0),
            )
            painter.drawLine(
                QPointF(center.x() - 1.0, center.y() + 3.0),
                QPointF(center.x() + 4.0, center.y() - 3.0),
            )
        else:
            pen = QPen(QColor(palette.border))
            pen.setWidthF(1.5)
            painter.setPen(pen)
            painter.setBrush(QColor(palette.surface))
            painter.drawEllipse(center, radius, radius)
