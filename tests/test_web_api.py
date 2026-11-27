"""HTTP-интерфейс: загрузка файлов, анализ, настройки и экспорт."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mts_templates.composition import Container, build_container
from mts_templates.infrastructure.config import load_settings
from mts_templates.presentation.api.app import create_app
from tests.fixtures import TEMPLATE_HEADERS, write_statistics_xlsx, write_templates_xlsx
from tests.test_analysis_integration import (
    ORDINARY_PACKAGE,
    TEMPLATED_PACKAGE,
    statistics_rows,
    template_rows,
)

XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.fixture
def container(tmp_path: Path) -> Iterator[Container]:
    settings = load_settings(data_dir=tmp_path / "data")
    built = build_container(tmp_path / "web.db", settings=settings)
    yield built
    built.database.close()


@pytest.fixture
def client(container: Container) -> Iterator[TestClient]:
    with TestClient(create_app(container)) as test_client:
        yield test_client


def _upload(client: TestClient, path: Path, url: str) -> dict[str, object]:
    with path.open("rb") as handle:
        response = client.post(url, files={"file": (path.name, handle, XLSX_MEDIA)})
    assert response.status_code == 200, response.text
    return response.json()


def _prepare_batch(client: TestClient, tmp_path: Path) -> str:
    statistics = write_statistics_xlsx(tmp_path / "statistics.xlsx", statistics_rows())
    report = _upload(client, statistics, "/api/imports/statistics")
    return str(report["batch"]["id"])


def _import_templates(client: TestClient, tmp_path: Path) -> None:
    templates = write_templates_xlsx(tmp_path / "templates.xlsx", template_rows())
    preview = _upload(client, templates, "/api/imports/templates/preview")
    response = client.post(
        "/api/imports/templates",
        data={"upload_id": str(preview["upload_id"])},
    )
    assert response.status_code == 200, response.text
    assert response.json()["imported"] == 1


def test_health_and_themes(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok"}

    themes = client.get("/api/themes").json()["themes"]
    assert len(themes) == 14
    assert themes[0]["id"] == "system"
    assert {"window", "surface", "positive"} <= set(themes[1]["palette"])


def test_statistics_import_and_dashboard(client: TestClient, tmp_path: Path) -> None:
    batch_id = _prepare_batch(client, tmp_path)

    batches = client.get("/api/batches").json()["batches"]
    assert [item["id"] for item in batches] == [batch_id]
    assert batches[0]["source_name"].endswith("statistics.xlsx")

    summary = client.get("/api/dashboard", params={"batch_id": batch_id}).json()
    assert summary["batch"]["id"] == batch_id
    assert summary["statistics"]["message_count"] == 9
    assert summary["statistics"]["segments"] == 9
    assert summary["statistics"]["cost"] == "75.20"
    assert len(summary["operators"]) == 1
    assert summary["operators"][0]["operator"] == "MTS"
    assert summary["daily_segments"][0]["day"] == "2026-11-01"
    assert summary["daily_segments"][0]["operators"][0]["operator"] == "MTS"


def test_batch_management_endpoints(client: TestClient, tmp_path: Path) -> None:
    batch_id = _prepare_batch(client, tmp_path)

    renamed = client.put(f"/api/batches/{batch_id}/name", json={"name": "Октябрь 2026"}).json()
    assert renamed["name"] == "Октябрь 2026"
    assert renamed["source_name"].endswith("statistics.xlsx")

    labeled = client.put(
        f"/api/batches/{batch_id}/period-label", json={"period_label": "Октябрь"}
    ).json()
    assert labeled["period_label"] == "Октябрь"
    assert labeled["source_name"].endswith("statistics.xlsx")

    batches = client.get("/api/batches").json()["batches"]
    assert batches[0]["name"] == "Октябрь 2026"
    assert batches[0]["period_label"] == "Октябрь"

    too_long = client.put(f"/api/batches/{batch_id}/name", json={"name": "а" * 201})
    assert too_long.status_code == 422

    missing = client.put("/api/batches/missing/name", json={"name": "Новое"})
    assert missing.status_code == 404

    analysis = client.post(
        "/api/analysis",
        json={"batch_id": batch_id, "include_candidates": True, "force": True},
    )
    assert analysis.status_code == 200

    assert client.delete(f"/api/batches/{batch_id}").json()["deleted"] == 1
    assert client.get("/api/batches").json()["batches"] == []
    assert client.delete("/api/batches").json()["deleted"] == 0


def test_templates_preview_and_import(client: TestClient, tmp_path: Path) -> None:
    templates = write_templates_xlsx(tmp_path / "templates.xlsx", template_rows())
    preview = _upload(client, templates, "/api/imports/templates/preview")

    assert preview["source_name"].endswith("templates.xlsx")
    assert "Текст шаблона" in preview["columns"]
    assert preview["sample_rows"][0]["Текст шаблона"] == "Ваш код %d"
    assert preview["suggested"]["text"] == "Текст шаблона"

    report = client.post(
        "/api/imports/templates",
        data={"upload_id": str(preview["upload_id"])},
    ).json()
    assert report["imported"] == 1

    listed = client.get("/api/templates").json()["templates"]
    assert [item["text"] for item in listed] == ["Ваш код %d"]
    assert listed[0]["monthly_fee"] == "2000.00"


def test_template_import_requires_excel(client: TestClient) -> None:
    response = client.post(
        "/api/imports/statistics",
        files={"file": ("statistics.csv", b"a,b", "text/csv")},
    )
    assert response.status_code == 415


def test_analysis_and_matched_messages(client: TestClient, tmp_path: Path) -> None:
    batch_id = _prepare_batch(client, tmp_path)
    _import_templates(client, tmp_path)

    response = client.post(
        "/api/analysis",
        json={"batch_id": batch_id, "include_candidates": True},
    )
    assert response.status_code == 200, response.text
    view = response.json()
    assert view["total_segments"] == 9
    assert view["templated_segments"] == 2
    assert view["is_partial_period"] is False
    assert view["daily_total_segments"][0] == {"day": "2026-11-01", "segments": 3}
    assert set(view["daily_total_segments"][0]) == {"day", "segments"}

    metrics = view["metrics"][0]
    assert metrics["text"] == "Ваш код %d"
    assert metrics["matched_messages"] == 2
    assert metrics["monthly_net_benefit"] == "-1988.80"
    assert metrics["daily_segments"] == [{"day": "2026-11-01", "segments": 2}]

    candidate = view["candidates"][0]
    assert candidate["template_text"] == "Заказ %d готов к выдаче"
    assert candidate["net_monthly"] == "-1966.40"
    assert candidate["confidence"] == pytest.approx(1.0)

    template_messages = client.get(
        f"/api/matched-messages/template/{metrics['template_id']}",
        params={"batch_id": batch_id},
    ).json()["messages"]
    assert len(template_messages) == 2
    assert template_messages[0]["text"].startswith("Ваш код ")
    assert template_messages[0]["masked_recipient"] != "79000000000"
    assert template_messages[0]["delivery_status"] == "Успешная доставка"

    candidate_messages = client.get(
        f"/api/matched-messages/candidate/{candidate['candidate_id']}",
        params={"batch_id": batch_id},
    ).json()["messages"]
    assert len(candidate_messages) == 6

    missing = client.get(
        "/api/matched-messages/candidate/unknown",
        params={"batch_id": batch_id},
    )
    assert missing.status_code == 404


def test_analysis_uses_cache(client: TestClient, tmp_path: Path) -> None:
    batch_id = _prepare_batch(client, tmp_path)
    body = {"batch_id": batch_id, "include_candidates": True}

    first = client.post("/api/analysis", json=body).json()
    second = client.post("/api/analysis", json=body).json()
    assert first["run_id"] == second["run_id"]


def test_action_center_and_drill_down(client: TestClient, tmp_path: Path) -> None:
    rows = statistics_rows()
    rows.append(
        {
            "ID сообщения": "B1",
            "Имя отправителя": "TEST",
            "Номер получателя": "79000000001",
            "Оператор получателя": "Beeline",
            "Дата попытки отправки": "2026-11-03T10:00:00+03:00",
            "Статус отправки": "Отправлено",
            "Статус доставки СМС или ММС": "Успешная доставка",
            "Текст сообщения": "Ваш код 3333",
            "Цена за один сегмент": 10,
            "Стоимость": 10,
            "Количество сегментов в sms": 1,
            "Тип пакета": ORDINARY_PACKAGE,
            "Канал": "SMS",
            "Количество sms в пакете при покупке": 999999999,
        }
    )
    rows.append(
        {
            "ID сообщения": "U1",
            "Имя отправителя": "TEST",
            "Номер получателя": "79000000002",
            "Оператор получателя": "MTS",
            "Дата попытки отправки": "2026-11-04T10:00:00+03:00",
            "Статус отправки": "Отправлено",
            "Статус доставки СМС или ММС": "Успешная доставка",
            "Текст сообщения": "Оплачено как шаблон без шаблона",
            "Цена за один сегмент": 5,
            "Стоимость": 5,
            "Количество сегментов в sms": 1,
            "Тип пакета": TEMPLATED_PACKAGE,
            "Канал": "SMS",
            "Количество sms в пакете при покупке": 999999999,
        }
    )

    statistics = write_statistics_xlsx(tmp_path / "statistics.xlsx", rows)
    report = _upload(client, statistics, "/api/imports/statistics")
    batch_id = str(report["batch"]["id"])

    templates = template_rows()
    templates[0]["Операторы"] = "МТС"
    templates_path = write_templates_xlsx(
        tmp_path / "templates.xlsx",
        templates,
        headers=(*TEMPLATE_HEADERS, "Операторы"),
    )
    preview = _upload(client, templates_path, "/api/imports/templates/preview")
    imported = client.post(
        "/api/imports/templates",
        data={"upload_id": str(preview["upload_id"])},
    )
    assert imported.status_code == 200, imported.text

    response = client.get("/api/action-center", params={"batch_id": batch_id})
    assert response.status_code == 200, response.text
    center = response.json()

    assert center["loss_templates"] == 1
    assert center["off_operator_messages"] == 1
    assert center["off_operator_loss"] == "5.67"
    assert center["unmatched_templated_messages"] == 1
    assert center["unmatched_templated_segments"] == 1
    assert center["unmatched_templated_cost"] == "5.00"
    assert center["total_monthly_loss"] == "1994.37"
    assert center["observed_templated_rate"] == "4.33"
    assert [item["kind"] for item in center["items"]] == [
        "loss_template",
        "off_operator",
        "unmatched_templated",
    ]

    loss_item, operator_item, unmatched_item = center["items"]
    assert loss_item["severity"] == 1
    assert loss_item["monthly_loss"] == "1988.70"
    assert loss_item["drill_down"] == "template"
    assert operator_item["operator"] == "Beeline"
    assert operator_item["monthly_loss"] == "5.67"
    assert unmatched_item["severity"] == 0
    assert unmatched_item["monthly_loss"] == "0.00"
    assert unmatched_item["drill_down"] == "unmatched_templated"

    template_messages = client.get(
        f"/api/matched-messages/template/{loss_item['template_id']}",
        params={"batch_id": batch_id, "operator": "Beeline", "untriggered": "true"},
    ).json()["messages"]
    assert len(template_messages) == 1
    assert template_messages[0]["operator"] == "Beeline"
    assert template_messages[0]["text"] == "Ваш код 3333"

    unmatched_messages = client.get(
        "/api/matched-messages/unmatched-templated",
        params={"batch_id": batch_id},
    ).json()["messages"]
    assert len(unmatched_messages) == 1
    assert unmatched_messages[0]["text"] == "Оплачено как шаблон без шаблона"


def test_settings_update(client: TestClient) -> None:
    initial = client.get("/api/settings").json()
    assert initial["baseline_mode"] == "observed"
    assert len(initial["benefit_thresholds"]) == 5

    response = client.put(
        "/api/settings",
        json={
            "theme": "dark_art_deco",
            "template_fee": "2500",
            "min_support": 4,
            "benefit_thresholds": ["1", "3000", "10000", "30000", "100000"],
        },
    )
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["theme"] == "dark_art_deco"
    assert updated["template_fee"] == "2500.00"
    assert updated["min_support"] == 4

    assert client.get("/api/settings").json()["theme"] == "dark_art_deco"

    invalid = client.put("/api/settings", json={"theme": "no_such_theme"})
    assert invalid.status_code == 422

    non_increasing = client.put(
        "/api/settings",
        json={"benefit_thresholds": ["1", "1", "2", "3", "4"]},
    )
    assert non_increasing.status_code == 422


def test_export_returns_xlsx(client: TestClient, tmp_path: Path) -> None:
    batch_id = _prepare_batch(client, tmp_path)
    _import_templates(client, tmp_path)
    client.post("/api/analysis", json={"batch_id": batch_id, "include_candidates": True})

    response = client.post("/api/export", json={"batch_id": batch_id})
    assert response.status_code == 200, response.text
    assert response.content[:2] == b"PK"
    assert "spreadsheetml" in response.headers["content-type"]
    assert "statistics" in response.headers["content-disposition"]

    unknown = client.post("/api/export", json={"batch_id": "missing"})
    assert unknown.status_code == 404


def test_spa_fallback(client: TestClient) -> None:
    response = client.get("/templates")
    assert response.status_code in {200, 503}
