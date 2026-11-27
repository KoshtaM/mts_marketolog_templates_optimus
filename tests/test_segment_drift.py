"""Пометка о дрейфе текста шаблона в мини-дашборде."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from mts_templates.presentation.desktop.theme import active_palette
from mts_templates.presentation.desktop.widgets.segment_dashboard import (
    DashboardDrift,
    DashboardDriftFragment,
    DriftNotice,
    _fragments_html,
)

_APP = QApplication.instance() or QApplication([])


def _drift() -> DashboardDrift:
    return DashboardDrift(
        similarity=0.8571,
        candidate_text="Ваш новый код %d",
        before=(
            DashboardDriftFragment(kind="equal", text="Ваш"),
            DashboardDriftFragment(kind="equal", text="код %d"),
        ),
        after=(
            DashboardDriftFragment(kind="equal", text="Ваш"),
            DashboardDriftFragment(kind="added", text="новый"),
            DashboardDriftFragment(kind="equal", text="код %d"),
        ),
    )


def test_fragments_html_highlights_removed_and_added_parts() -> None:
    fragments = (
        DashboardDriftFragment(kind="equal", text="Ваш"),
        DashboardDriftFragment(kind="removed", text="код"),
        DashboardDriftFragment(kind="added", text="пароль"),
    )

    markup = _fragments_html(fragments, active_palette())

    assert markup.startswith("Ваш ")
    assert "line-through" in markup
    assert "font-weight: 600" in markup
    assert markup.index("код") < markup.index("пароль")


def test_fragments_html_escapes_text() -> None:
    fragments = (DashboardDriftFragment(kind="added", text="<b>x</b>"),)

    markup = _fragments_html(fragments, active_palette())

    assert "<b>" not in markup
    assert "&lt;b&gt;x&lt;/b&gt;" in markup


def test_drift_notice_is_hidden_without_drift() -> None:
    notice = DriftNotice()

    notice.set_drift(None)

    assert notice.isHidden()


def test_drift_notice_shows_similarity_and_places_of_change() -> None:
    notice = DriftNotice()

    notice.set_drift(_drift())

    assert not notice.isHidden()
    assert "86 %" in notice._title.text()
    assert "line-through" not in notice._before.text()
    assert "новый" in notice._after.text()
    assert notice._title.toolTip() == "Ваш новый код %d"
