"""FastAPI-приложение: тонкий HTTP-адаптер над application use cases."""

from __future__ import annotations

import json
import os
import shutil
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from mts_templates.application.dto import (
    AnalyzeRequest,
    ExportReportRequest,
    ImportBatch,
    ImportStatisticsRequest,
    ImportTemplatesRequest,
    MatchedMessageView,
    TemplateColumnMapping,
)
from mts_templates.application.settings import (
    BASELINE_MODES,
    THEME_IDS,
    AppSettings,
    BenefitThresholds,
)
from mts_templates.composition import Container, build_container
from mts_templates.domain.analytics.normalization import PUNCTUATION_POLICIES
from mts_templates.domain.errors import DomainError
from mts_templates.domain.value_objects import Money
from mts_templates.presentation.api.serializers import (
    action_center_to_dict,
    analysis_to_dict,
    batch_to_dict,
    dashboard_to_dict,
    import_report_to_dict,
    settings_to_dict,
    template_import_report_to_dict,
    template_preview_to_dict,
    template_to_dict,
    template_trend_to_dict,
    theme_to_dict,
)
from mts_templates.presentation.desktop.theme_catalog import SYSTEM_THEME, THEMES

API_PREFIX = "/api"
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
EXCEL_SUFFIXES = {".xlsx", ".xlsm"}


class AnalyzeBody(BaseModel):
    batch_id: str = Field(min_length=1)
    include_candidates: bool = True
    force: bool = False


class ExportBody(BaseModel):
    batch_id: str = Field(min_length=1)


class BatchNameBody(BaseModel):
    name: str | None = Field(default=None, max_length=200)


class BatchPeriodLabelBody(BaseModel):
    period_label: str | None = Field(default=None, max_length=100)


class SettingsUpdate(BaseModel):
    template_fee: str | None = None
    min_support: int | None = None
    min_cluster_segments: int | None = None
    min_text_length: int | None = None
    max_foreign_matches: int | None = None
    max_w_words: int | None = None
    max_d_words: int | None = None
    max_word_slots_per_merge: int | None = None
    max_literal_cardinality: int | None = None
    max_tail_depth: int | None = None
    punctuation_policy: str | None = None
    fold_yo: bool | None = None
    fold_homoglyphs: bool | None = None
    sender_case_sensitive: bool | None = None
    baseline_mode: str | None = None
    delivered_only: bool | None = None
    benefit_thresholds: list[str] | None = None
    theme: str | None = None


def create_app(container: Container | None = None) -> FastAPI:
    """Собрать приложение; тесты передают готовый контейнер."""
    app = FastAPI(
        title="MTS Templates Optimus API",
        version="0.1.0",
        description="Локальный HTTP-интерфейс анализа SMS-шаблонов.",
    )
    app.state.container = container or build_container()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=("http://localhost:5173", "http://127.0.0.1:5173"),
        allow_credentials=False,
        allow_methods=("*",),
        allow_headers=("*",),
    )

    @app.exception_handler(DomainError)
    async def _domain_error(_request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def _value_error(_request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    _register_routes(app)
    _mount_frontend(app)
    return app


def _register_routes(app: FastAPI) -> None:
    @app.get(f"{API_PREFIX}/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get(f"{API_PREFIX}/themes")
    def themes() -> dict[str, Any]:
        catalog = (SYSTEM_THEME, *THEMES)
        return {"themes": [theme_to_dict(theme) for theme in catalog]}

    @app.get(f"{API_PREFIX}/settings")
    def read_settings(container: Container = Depends(_get_container)) -> dict[str, Any]:
        return settings_to_dict(container.settings_store.load())

    @app.put(f"{API_PREFIX}/settings")
    def update_settings(
        payload: SettingsUpdate,
        container: Container = Depends(_get_container),
    ) -> dict[str, Any]:
        current = container.settings_store.load()
        updated = _apply_settings(current, payload)
        container.settings_store.save(updated)
        return settings_to_dict(updated)

    @app.get(f"{API_PREFIX}/batches")
    def list_batches(container: Container = Depends(_get_container)) -> dict[str, Any]:
        return {"batches": [batch_to_dict(item) for item in container.list_batches.execute()]}

    @app.put(f"{API_PREFIX}/batches/{{batch_id}}/name")
    def rename_batch(
        batch_id: str,
        payload: BatchNameBody,
        container: Container = Depends(_get_container),
    ) -> dict[str, Any]:
        batch = container.rename_batch.execute(batch_id, payload.name)
        if batch is None:
            raise HTTPException(status_code=404, detail="Загрузка статистики не найдена")
        return batch_to_dict(batch)

    @app.put(f"{API_PREFIX}/batches/{{batch_id}}/period-label")
    def set_batch_period_label(
        batch_id: str,
        payload: BatchPeriodLabelBody,
        container: Container = Depends(_get_container),
    ) -> dict[str, Any]:
        batch = container.set_batch_period_label.execute(batch_id, payload.period_label)
        if batch is None:
            raise HTTPException(status_code=404, detail="Загрузка статистики не найдена")
        return batch_to_dict(batch)

    @app.delete(f"{API_PREFIX}/batches/{{batch_id}}")
    def delete_batch(
        batch_id: str,
        container: Container = Depends(_get_container),
    ) -> dict[str, int]:
        if not container.delete_batch.execute(batch_id):
            raise HTTPException(status_code=404, detail="Загрузка статистики не найдена")
        return {"deleted": 1}

    @app.delete(f"{API_PREFIX}/batches")
    def delete_all_batches(container: Container = Depends(_get_container)) -> dict[str, int]:
        return {"deleted": container.delete_all_batches.execute()}

    @app.get(f"{API_PREFIX}/dashboard")
    def dashboard(
        batch_id: str | None = None,
        container: Container = Depends(_get_container),
    ) -> dict[str, Any]:
        return dashboard_to_dict(container.dashboard.execute(batch_id))

    @app.get(f"{API_PREFIX}/templates")
    def list_templates(container: Container = Depends(_get_container)) -> dict[str, Any]:
        return {
            "templates": [template_to_dict(item) for item in container.list_templates.execute()]
        }

    @app.get(f"{API_PREFIX}/templates/{{template_id}}/trend")
    def template_trend(
        template_id: str,
        container: Container = Depends(_get_container),
    ) -> dict[str, Any]:
        trend = container.template_trend.execute(template_id)
        return template_trend_to_dict(trend)

    @app.post(f"{API_PREFIX}/imports/statistics")
    def import_statistics(
        file: UploadFile = File(...),
        container: Container = Depends(_get_container),
    ) -> dict[str, Any]:
        path = _save_upload(file, container, "statistics")
        report = container.import_statistics.execute(ImportStatisticsRequest(path=path))
        return import_report_to_dict(report)

    @app.post(f"{API_PREFIX}/imports/templates/preview")
    def preview_templates(
        file: UploadFile = File(...),
        container: Container = Depends(_get_container),
    ) -> dict[str, Any]:
        path = _save_upload(file, container, "templates")
        preview = container.preview_templates.execute(path)
        result = template_preview_to_dict(preview)
        result["upload_id"] = path.name
        return result

    @app.post(f"{API_PREFIX}/imports/templates")
    def import_templates(
        upload_id: str | None = Form(None),
        mapping_json: str | None = Form(None),
        file: UploadFile | None = File(None),
        container: Container = Depends(_get_container),
    ) -> dict[str, Any]:
        path = _resolve_upload(container, upload_id) if upload_id else None
        if path is None:
            if file is None:
                raise HTTPException(status_code=422, detail="Нужен файл шаблонов")
            path = _save_upload(file, container, "templates")
        mapping = _parse_mapping(mapping_json)
        report = container.import_templates.execute(
            ImportTemplatesRequest(path=path, mapping=mapping)
        )
        return template_import_report_to_dict(report)

    @app.post(f"{API_PREFIX}/analysis")
    def analyze(
        payload: AnalyzeBody,
        container: Container = Depends(_get_container),
    ) -> dict[str, Any]:
        view = container.analyze_templates.execute(
            AnalyzeRequest(
                batch_id=payload.batch_id,
                include_candidates=payload.include_candidates,
                force=payload.force,
            )
        )
        return analysis_to_dict(view)

    @app.get(f"{API_PREFIX}/action-center")
    def action_center(
        batch_id: str,
        force: bool = False,
        container: Container = Depends(_get_container),
    ) -> dict[str, Any]:
        return action_center_to_dict(container.action_center.execute(batch_id, force=force))

    @app.get(f"{API_PREFIX}/matched-messages/template/{{template_id}}")
    def matched_template_messages(
        template_id: str,
        batch_id: str,
        operator: str | None = None,
        untriggered: bool = False,
        container: Container = Depends(_get_container),
    ) -> dict[str, Any]:
        messages = container.matched_messages.for_template(
            batch_id,
            template_id,
            operator=operator,
            untriggered_only=untriggered,
        )
        return {"messages": [_message_to_dict(item) for item in messages]}

    @app.get(f"{API_PREFIX}/matched-messages/unmatched-templated")
    def unmatched_templated_messages(
        batch_id: str,
        container: Container = Depends(_get_container),
    ) -> dict[str, Any]:
        messages = container.matched_messages.unmatched_templated(batch_id)
        return {"messages": [_message_to_dict(item) for item in messages]}

    @app.get(f"{API_PREFIX}/matched-messages/candidate/{{candidate_id}}")
    def matched_candidate_messages(
        candidate_id: str,
        batch_id: str,
        container: Container = Depends(_get_container),
    ) -> dict[str, Any]:
        view = container.analyze_templates.execute(
            AnalyzeRequest(batch_id=batch_id, include_candidates=True)
        )
        candidate = next(
            (item for item in view.candidates if item.candidate_id == candidate_id),
            None,
        )
        if candidate is None:
            raise HTTPException(status_code=404, detail="Кандидат не найден")
        messages = container.matched_messages.for_candidate(batch_id, candidate)
        return {"messages": [_message_to_dict(item) for item in messages]}

    @app.post(f"{API_PREFIX}/export")
    def export_report(
        payload: ExportBody,
        container: Container = Depends(_get_container),
    ) -> FileResponse:
        batch = _find_batch(container, payload.batch_id)
        exports = _data_dir(container) / "exports"
        exports.mkdir(parents=True, exist_ok=True)
        target = exports / f"mts-report-{batch.id[:8]}-{uuid.uuid4().hex[:8]}.xlsx"
        container.export_report.execute(ExportReportRequest(path=target, batch_id=payload.batch_id))
        source_name = Path(batch.source_path).stem
        return FileResponse(
            target,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=f"mts-report-{source_name}.xlsx",
        )


def _get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


def _data_dir(container: Container) -> Path:
    return container.settings_store.load().data_dir


def _uploads_dir(container: Container) -> Path:
    directory = _data_dir(container) / "uploads"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _save_upload(upload: UploadFile, container: Container, prefix: str) -> Path:
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in EXCEL_SUFFIXES:
        raise HTTPException(
            status_code=415,
            detail="Поддерживаются только файлы Excel (.xlsx, .xlsm)",
        )
    if upload.size is not None and upload.size > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Файл больше 100 МБ")
    original = Path(upload.filename or "").name or f"upload{suffix}"
    target = _uploads_dir(container) / f"{prefix}-{uuid.uuid4().hex}-{original}"
    upload.file.seek(0)
    with target.open("wb") as handle:
        shutil.copyfileobj(upload.file, handle)
    return target


def _resolve_upload(container: Container, upload_id: str) -> Path | None:
    name = Path(upload_id).name
    if name != upload_id:
        raise HTTPException(status_code=400, detail="Некорректный идентификатор файла")
    path = _uploads_dir(container) / name
    return path if path.is_file() else None


def _parse_mapping(raw: str | None) -> TemplateColumnMapping | None:
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="Некорректное сопоставление колонок") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="Некорректное сопоставление колонок")
    text = str(payload.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="Не выбрана колонка с текстом шаблона")
    fields = (
        "template_id",
        "name",
        "sender",
        "active",
        "monthly_fee",
        "operators",
        "example",
        "traffic_type",
    )
    values = {
        field: str(payload[field]).strip()
        for field in fields
        if payload.get(field) not in (None, "")
    }
    return TemplateColumnMapping(text=text, **values)


def _apply_settings(current: AppSettings, payload: SettingsUpdate) -> AppSettings:
    changes: dict[str, Any] = {}
    if payload.template_fee is not None:
        try:
            changes["template_fee"] = Money(Decimal(payload.template_fee.replace(",", ".")))
        except (InvalidOperation, ValueError) as exc:
            raise HTTPException(status_code=422, detail="Некорректная стоимость шаблона") from exc
    integer_fields = (
        "min_support",
        "min_cluster_segments",
        "min_text_length",
        "max_foreign_matches",
        "max_w_words",
        "max_d_words",
        "max_word_slots_per_merge",
        "max_literal_cardinality",
        "max_tail_depth",
    )
    for field in integer_fields:
        value = getattr(payload, field)
        if value is not None:
            minimum = 0 if field == "max_foreign_matches" else 1
            changes[field] = max(minimum, value)
    if payload.punctuation_policy is not None:
        if payload.punctuation_policy not in PUNCTUATION_POLICIES:
            raise HTTPException(status_code=422, detail="Неизвестная политика пунктуации")
        changes["punctuation_policy"] = payload.punctuation_policy
    for field in ("fold_yo", "fold_homoglyphs", "sender_case_sensitive", "delivered_only"):
        value = getattr(payload, field)
        if value is not None:
            changes[field] = value
    if payload.baseline_mode is not None:
        if payload.baseline_mode not in BASELINE_MODES:
            raise HTTPException(status_code=422, detail="Неизвестная модель baseline")
        changes["baseline_mode"] = payload.baseline_mode
    if payload.theme is not None:
        if payload.theme not in THEME_IDS:
            raise HTTPException(status_code=422, detail="Неизвестная тема оформления")
        changes["theme"] = payload.theme
    if payload.benefit_thresholds is not None:
        if len(payload.benefit_thresholds) != 5:
            raise HTTPException(status_code=422, detail="Нужно ровно пять порогов выгоды")
        try:
            levels = [Money(Decimal(item.replace(",", "."))) for item in payload.benefit_thresholds]
            changes["benefit_thresholds"] = BenefitThresholds(
                level_1=levels[0],
                level_2=levels[1],
                level_3=levels[2],
                level_4=levels[3],
                level_5=levels[4],
            )
        except (InvalidOperation, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail="Пороги выгод должны быть числами и строго возрастать",
            ) from exc
    return current.with_overrides(**changes) if changes else current


def _find_batch(container: Container, batch_id: str) -> ImportBatch:
    batch = next(
        (item for item in container.list_batches.execute() if item.id == batch_id),
        None,
    )
    if batch is None:
        raise HTTPException(status_code=404, detail="Загрузка статистики не найдена")
    return batch


def _message_to_dict(item: MatchedMessageView) -> dict[str, Any]:
    return {
        "message_id": item.message_id,
        "text": item.text,
        "segments": item.segments,
        "masked_recipient": item.masked_recipient,
        "sent_at": item.sent_at.isoformat(),
        "operator": item.operator,
        "delivery_status": item.delivery_status,
    }


def _mount_frontend(app: FastAPI) -> None:
    dist = Path(os.environ.get("MTS_WEB_DIST", "")) if os.environ.get("MTS_WEB_DIST") else None
    if dist is None:
        dist = Path(__file__).resolve().parents[4] / "frontend" / "dist"
    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> Any:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Маршрут API не найден")
        index = dist / "index.html"
        if index.is_file():
            return FileResponse(index)
        return JSONResponse(
            {
                "detail": "Веб-клиент не собран. Выполните `npm install && npm run build` "
                "в каталоге frontend или запустите `npm run dev`."
            },
            status_code=503,
        )
