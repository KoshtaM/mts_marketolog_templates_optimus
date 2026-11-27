"""DTO слоя приложения: запросы, отчёты, метаданные импорта и представления."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from mts_templates.domain.analytics.activity import DaySegments
from mts_templates.domain.analytics.import_aggregation import QualityIssue
from mts_templates.domain.analytics.normalization import NormalizationPolicy
from mts_templates.domain.entities import SmsMessage, SmsTemplate
from mts_templates.domain.value_objects import Money


@dataclass(frozen=True, slots=True)
class ImportStatisticsRequest:
    path: Path


@dataclass(frozen=True, slots=True)
class ImportBatch:
    """Метаданные одной загрузки файла статистики."""

    id: str
    source_path: str
    source_sha256: str
    kind: str
    imported_at: datetime
    row_count: int
    message_count: int
    total_cost: Money
    period_from: datetime | None
    period_to: datetime | None
    status: str
    name: str | None = None
    period_label: str | None = None
    warnings: tuple[str, ...] = ()
    segment_count: int = 0
    duplicate_message_ids: int = 0
    delivered_rows: int = 0
    partial_delivered_rows: int = 0
    send_error_rows: int = 0
    delivery_error_rows: int = 0
    empty_package_rows: int = 0


@dataclass(frozen=True, slots=True)
class ImportReport:
    """Результат импорта для UI и логов."""

    batch: ImportBatch
    reused: bool
    duplicate_message_ids: int
    segment_count: int
    delivered_rows: int
    partial_delivered_rows: int
    send_error_rows: int
    delivery_error_rows: int
    empty_package_rows: int
    issues: tuple[QualityIssue, ...]

    @property
    def has_issues(self) -> bool:
        return bool(self.issues or self.batch.warnings)


@dataclass(frozen=True, slots=True)
class StoredStatistics:
    """Готовые к сохранению данные импорта."""

    batch: ImportBatch
    messages: tuple[SmsMessage, ...]


@dataclass(frozen=True, slots=True)
class TemplateColumnMapping:
    """Какие колонки Excel-файла шаблонов во что превращаются."""

    text: str
    template_id: str | None = None
    name: str | None = None
    sender: str | None = None
    active: str | None = None
    monthly_fee: str | None = None
    operators: str | None = None
    example: str | None = None
    traffic_type: str | None = None


@dataclass(frozen=True, slots=True)
class TemplateFilePreview:
    """Первые строки файла шаблонов для диалога сопоставления колонок."""

    path: Path
    columns: tuple[str, ...]
    sample_rows: tuple[dict[str, str], ...]
    suggested: TemplateColumnMapping | None = None


@dataclass(frozen=True, slots=True)
class ImportTemplatesRequest:
    path: Path
    mapping: TemplateColumnMapping | None = None


@dataclass(frozen=True, slots=True)
class TemplateReadResult:
    """Шаблоны, прочитанные из файла, и предупреждения по строкам."""

    templates: tuple[SmsTemplate, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TemplateImportReport:
    imported: int
    updated: int
    duplicates: int
    skipped_empty: int
    warnings: tuple[str, ...] = ()
    removed: int = 0


@dataclass(frozen=True, slots=True)
class AnalyzeRequest:
    """Запрос прогона анализа по загруженной статистике."""

    batch_id: str
    include_candidates: bool = True
    force: bool = False


@dataclass(frozen=True, slots=True)
class AnalysisConfig:
    """Параметры анализа, влияющие на результат и хэш конфигурации."""

    baseline_mode: str = "observed"
    delivered_only: bool = True
    min_support: int = 5
    min_cluster_segments: int = 5
    min_text_length: int = 8
    max_foreign_matches: int = 0
    max_w_words: int = 20
    max_d_words: int = 20
    max_word_slots_per_merge: int = 20
    max_literal_cardinality: int = 3
    max_tail_depth: int = 4
    punctuation_policy: str = "delete"
    fold_yo: bool = False
    fold_homoglyphs: bool = False
    sender_case_sensitive: bool = False
    template_fee: Money = field(default_factory=lambda: Money.from_rub("2000.00"))

    def normalization_policy(self) -> NormalizationPolicy:
        """Политика нормализации текста и шаблонов."""
        return NormalizationPolicy(
            punctuation=self.punctuation_policy,
            fold_yo=self.fold_yo,
            fold_homoglyphs=self.fold_homoglyphs,
        )


@dataclass(frozen=True, slots=True)
class TemplateMetricsView:
    """Метрики шаблона, дополненные его реквизитами для UI."""

    template_id: str
    name: str
    sender: str
    text: str
    operators: tuple[str, ...]
    active: bool
    matched_messages: int
    matched_segments: int
    delivered_messages: int
    unique_recipients: int
    triggered_messages: int
    off_operator_messages: int
    actual_cost: Money
    baseline_cost: Money
    template_fee: Money
    net_benefit: Money
    trigger_rate: float
    monthly_messages: int
    monthly_segments: int
    monthly_actual_cost: Money
    monthly_baseline_cost: Money
    monthly_net_benefit: Money
    share_of_all_segments: float
    share_of_templated_segments: float
    daily_segments: tuple[DaySegments, ...] = ()


@dataclass(frozen=True, slots=True)
class OperatorTriggerView:
    """Срабатывание шаблона у одного оператора получателя."""

    template_id: str
    template_name: str
    sender: str
    operator: str
    listed: bool
    matched_messages: int
    triggered_messages: int
    matched_segments: int = 0
    share: float = 0.0

    @property
    def trigger_rate(self) -> float:
        return self.triggered_messages / self.matched_messages if self.matched_messages else 0.0


@dataclass(frozen=True, slots=True)
class OperatorStatistics:
    """Агрегаты по оператору получателя для дашборда."""

    operator: str
    messages: int
    segments: int
    cost: Money

    @property
    def average_segment_cost(self) -> Money | None:
        """Средняя стоимость одного SMS-сегмента у оператора."""
        return self.cost / self.segments if self.segments else None


@dataclass(frozen=True, slots=True)
class DailyOperatorSegments:
    """SMS-сегменты одного оператора получателя за календарный день."""

    operator: str
    segments: int


@dataclass(frozen=True, slots=True)
class DailySegments:
    """Сегменты дня с разбивкой по операторам, по убыванию объёма.

    Дни без отправок присутствуют с пустым списком операторов: ось X
    диаграммы должна покрывать весь период загрузки без пропусков.
    """

    day: date
    operators: tuple[DailyOperatorSegments, ...] = ()

    @property
    def segments(self) -> int:
        return sum(item.segments for item in self.operators)


@dataclass(frozen=True, slots=True)
class SegmentCountBucket:
    """Сколько абонентов или сообщений приходится на заданное число SMS-сегментов."""

    segments: int
    count: int
    share: float


@dataclass(frozen=True, slots=True)
class SubscriberOperatorShare:
    """Уникальные абоненты одного оператора получателя."""

    operator: str
    subscribers: int
    share: float


@dataclass(frozen=True, slots=True)
class SegmentationStatistics:
    """Уникальные абоненты загрузки и распределения по SMS-сегментам.

    Абонент — уникальный номер получателя, на который ушёл хотя бы один сегмент.
    Сообщения с нулём сегментов (ошибка отправки) в распределения не входят,
    их количество считается отдельно.
    """

    subscribers: int
    subscriber_segments: int
    subscriber_messages: int
    subscribers_by_segments: tuple[SegmentCountBucket, ...]
    subscribers_by_operator: tuple[SubscriberOperatorShare, ...]
    messages_by_segments: tuple[SegmentCountBucket, ...]
    zero_segment_messages: int

    @property
    def average_subscriber_segments(self) -> float:
        """Среднее число SMS-сегментов на абонента."""
        return self.subscriber_segments / self.subscribers if self.subscribers else 0.0

    @property
    def average_subscriber_messages(self) -> float:
        """Среднее число сообщений на абонента."""
        return self.subscriber_messages / self.subscribers if self.subscribers else 0.0


@dataclass(frozen=True, slots=True)
class CandidateView:
    """Кандидат на регистрацию шаблона в виде, удобном для UI."""

    candidate_id: str
    template_text: str
    messages: int
    segments: int
    actual_cost: Money
    templated_cost: Money
    monthly_messages: int
    monthly_segments: int
    monthly_actual_cost: Money
    monthly_templated_cost: Money
    monthly_saving: Money
    template_fee: Money
    net_monthly: Money
    payback_months: float | None
    confidence: float
    coverage: float
    senders: tuple[str, ...]
    operators: tuple[str, ...]
    period_from: datetime
    period_to: datetime
    is_partial_period: bool
    examples: tuple[str, ...]
    status: str = "auto_validated"
    warnings: tuple[str, ...] = ()
    foreign_matches: int = 0
    share_of_all_segments: float = 0.0
    daily_segments: tuple[DaySegments, ...] = ()


@dataclass(frozen=True, slots=True)
class MatchedMessageView:
    """Реальная отправка загрузки, подпавшая под шаблон или шаблон-кандидат."""

    message_id: str
    text: str
    segments: int
    masked_recipient: str
    sent_at: datetime
    operator: str
    delivery_status: str


@dataclass(frozen=True, slots=True)
class AnalysisView:
    """Результат прогона анализа для экранов «Шаблоны» и «Кандидаты»."""

    run_id: str
    batch_id: str
    created_at: datetime
    period_from: datetime
    period_to: datetime
    message_count: int
    matched_message_count: int
    triggered_message_count: int
    total_net_benefit: Money
    inactive_templates: int
    trigger_rate: float
    metrics: tuple[TemplateMetricsView, ...]
    candidates: tuple[CandidateView, ...]
    warnings: tuple[str, ...] = ()
    operator_triggers: tuple[OperatorTriggerView, ...] = ()
    is_partial_period: bool = False
    daily_total_segments: tuple[DaySegments, ...] = ()
    daily_templated_segments: tuple[DaySegments, ...] = ()

    @property
    def total_monthly_net_benefit(self) -> Money:
        """Суммарная выгода шаблонов в месяц с учётом месячной модели периода."""
        return sum((item.monthly_net_benefit for item in self.metrics), Money.zero())

    @property
    def total_segments(self) -> int:
        """SMS-сегменты всех сообщений за период."""
        return sum(item.segments for item in self.daily_total_segments)

    @property
    def templated_segments(self) -> int:
        """SMS-сегменты шаблонированных сообщений за период."""
        return sum(item.segments for item in self.daily_templated_segments)


@dataclass(frozen=True, slots=True)
class ActionItemView:
    """Пункт центра действий: проблема или возможность, сумма и действие."""

    key: str
    kind: str
    severity: int
    title: str
    subject: str
    template_id: str | None
    template_name: str
    operator: str | None
    detail: str
    recommendation: str
    monthly_loss: Money
    monthly_benefit: Money
    messages: int
    segments: int
    drill_down: str | None
    action: str | None = None


@dataclass(frozen=True, slots=True)
class ActionCenterView:
    """Рабочий список убытков и возможностей по выбранной загрузке."""

    batch_id: str
    period_from: datetime
    period_to: datetime
    is_partial_period: bool
    monthly_factor: float
    total_monthly_loss: Money
    total_monthly_benefit: Money
    loss_templates: int
    profitable_candidates: int
    unmatched_templated_messages: int
    unmatched_templated_segments: int
    unmatched_templated_cost: Money
    observed_ordinary_rate: Money | None
    observed_templated_rate: Money | None
    items: tuple[ActionItemView, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BatchStatistics:
    """Агрегаты по загрузке, посчитанные в SQL."""

    message_count: int
    segments: int
    cost: Money
    delivered: int
    ordinary_messages: int
    ordinary_segments: int
    ordinary_cost: Money
    ordinary_rate: Money | None
    templated_messages: int
    templated_segments: int
    templated_cost: Money
    templated_rate: Money | None
    senders: int

    @property
    def average_cost(self) -> Money | None:
        """Средняя стоимость одного SMS за период."""
        return self.cost / self.message_count if self.message_count else None

    @property
    def ordinary_average_cost(self) -> Money | None:
        return self.ordinary_cost / self.ordinary_messages if self.ordinary_messages else None

    @property
    def templated_average_cost(self) -> Money | None:
        return self.templated_cost / self.templated_messages if self.templated_messages else None

    @property
    def average_segment_cost(self) -> Money | None:
        """Средняя стоимость одного SMS-сегмента за период."""
        return self.cost / self.segments if self.segments else None

    @property
    def ordinary_average_segment_cost(self) -> Money | None:
        return self.ordinary_cost / self.ordinary_segments if self.ordinary_segments else None

    @property
    def templated_average_segment_cost(self) -> Money | None:
        return self.templated_cost / self.templated_segments if self.templated_segments else None

    @property
    def delivered_share(self) -> float:
        """Доля доставленных сообщений в общем количестве."""
        return self.delivered / self.message_count if self.message_count else 0.0

    @property
    def ordinary_share(self) -> float:
        """Доля обычных сообщений в общем количестве."""
        return self.ordinary_messages / self.message_count if self.message_count else 0.0

    @property
    def templated_share(self) -> float:
        """Доля шаблонированных сообщений в общем количестве."""
        return self.templated_messages / self.message_count if self.message_count else 0.0

    @property
    def ordinary_segment_share(self) -> float:
        """Доля SMS-сегментов обычных сообщений."""
        return self.ordinary_segments / self.segments if self.segments else 0.0

    @property
    def templated_segment_share(self) -> float:
        """Доля SMS-сегментов шаблонированных сообщений."""
        return self.templated_segments / self.segments if self.segments else 0.0

    @property
    def average_segments(self) -> float:
        """Средняя длина сообщения в SMS-сегментах."""
        return self.segments / self.message_count if self.message_count else 0.0


@dataclass(frozen=True, slots=True)
class DashboardSummary:
    """Сводка для дашборда."""

    batches: tuple[ImportBatch, ...]
    batch: ImportBatch | None
    statistics: BatchStatistics | None
    template_count: int
    active_templates: int
    inactive_templates: int
    candidates: int
    total_monthly_net_benefit: Money | None
    profitable_candidates: int = 0
    profitable_candidates_benefit: Money | None = None
    loss_templates_benefit: Money | None = None
    potential_benefit: Money | None = None
    warnings: tuple[str, ...] = ()
    operators: tuple[OperatorStatistics, ...] = ()
    segmentation: SegmentationStatistics | None = None
    daily_segments: tuple[DailySegments, ...] = ()


@dataclass(frozen=True, slots=True)
class ExportReportRequest:
    path: Path
    batch_id: str


@dataclass(frozen=True, slots=True)
class ReportBundle:
    """Всё, что нужно для Excel-отчёта, без доступа к БД из адаптера."""

    batch: ImportBatch
    statistics: BatchStatistics
    analysis: AnalysisView | None
    baseline_mode: str
    template_fee: Money
    generated_at: datetime
    operators: tuple[OperatorStatistics, ...] = ()
    segmentation: SegmentationStatistics | None = None
    daily_segments: tuple[DailySegments, ...] = ()


@dataclass(frozen=True, slots=True)
class ExportReportResult:
    path: Path
    templates: int
    candidates: int
