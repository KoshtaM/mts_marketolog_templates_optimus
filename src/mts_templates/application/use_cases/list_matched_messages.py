"""Список реальных сообщений, подпавших под шаблон или шаблон-кандидат."""

from __future__ import annotations

from collections.abc import Callable

from mts_templates.application.dto import AnalysisConfig, CandidateView, MatchedMessageView
from mts_templates.application.ports import MessageQueryRepository, TemplateRepository
from mts_templates.domain.analytics.matching import (
    compile_templates,
    is_candidate_message,
    matches_candidate_pattern,
    resolve_template,
)
from mts_templates.domain.analytics.normalization import mask_phone, sender_key
from mts_templates.domain.analytics.template_syntax import compile_pattern
from mts_templates.domain.entities import SmsMessage
from mts_templates.domain.errors import OperationCancelled, TemplateSyntaxError
from mts_templates.domain.value_objects import MessageClass

UNKNOWN_STATUS = "Статус не указан"


class ListMatchedMessages:
    """Подбирает сообщения загрузки теми же правилами, что и прогон анализа."""

    def __init__(
        self,
        messages: MessageQueryRepository,
        templates: TemplateRepository,
        config_provider: Callable[[], AnalysisConfig],
    ) -> None:
        self._messages = messages
        self._templates = templates
        self._config_provider = config_provider

    def for_template(
        self,
        batch_id: str,
        template_id: str,
        *,
        operator: str | None = None,
        untriggered_only: bool = False,
        should_cancel: Callable[[], bool] | None = None,
    ) -> tuple[MatchedMessageView, ...]:
        """Все сообщения, подпавшие под шаблон: и сработавшие, и оплаченные как обычные.

        `operator` и `untriggered_only` сужают выборку для центра действий:
        показываем именно те сообщения, из-за которых возникла проблема.
        """
        config = self._config_provider()
        policy = config.normalization_policy()
        compiled = compile_templates(
            (item for item in self._templates.list_all() if item.active),
            policy,
            sender_case_sensitive=config.sender_case_sensitive,
        )
        result: list[MatchedMessageView] = []
        for message in self._messages.iter_messages(batch_id):
            _raise_if_cancelled(should_cancel)
            if message.segments <= 0:
                continue
            template = resolve_template(
                message,
                compiled,
                policy,
                sender_case_sensitive=config.sender_case_sensitive,
            )
            if template is None or template.template_id != template_id:
                continue
            if operator is not None and message.operator.value != operator:
                continue
            if untriggered_only and message.message_class is not MessageClass.ORDINARY:
                continue
            result.append(_to_view(message))
        return tuple(result)

    def unmatched_templated(
        self,
        batch_id: str,
        *,
        should_cancel: Callable[[], bool] | None = None,
    ) -> tuple[MatchedMessageView, ...]:
        """Сообщения, оплаченные как шаблонированные, но не подпавшие ни под один шаблон."""
        config = self._config_provider()
        policy = config.normalization_policy()
        compiled = compile_templates(
            (item for item in self._templates.list_all() if item.active),
            policy,
            sender_case_sensitive=config.sender_case_sensitive,
        )
        result: list[MatchedMessageView] = []
        for message in self._messages.iter_messages(batch_id):
            _raise_if_cancelled(should_cancel)
            if message.segments <= 0:
                continue
            if message.message_class is not MessageClass.TEMPLATED:
                continue
            if (
                resolve_template(
                    message,
                    compiled,
                    policy,
                    sender_case_sensitive=config.sender_case_sensitive,
                )
                is not None
            ):
                continue
            result.append(_to_view(message))
        return tuple(result)

    def for_candidate(
        self,
        batch_id: str,
        candidate: CandidateView,
        *,
        should_cancel: Callable[[], bool] | None = None,
    ) -> tuple[MatchedMessageView, ...]:
        """Сообщения, из которых собран кандидат: полное совпадение с его отправителями."""
        config = self._config_provider()
        policy = config.normalization_policy()
        try:
            pattern = compile_pattern(candidate.template_text, policy)
        except TemplateSyntaxError:
            return ()
        sender_keys = frozenset(
            sender_key(item, case_sensitive=config.sender_case_sensitive)
            for item in candidate.senders
        )
        compiled = compile_templates(
            (item for item in self._templates.list_all() if item.active),
            policy,
            sender_case_sensitive=config.sender_case_sensitive,
        )
        result: list[MatchedMessageView] = []
        for message in self._messages.iter_messages(batch_id):
            _raise_if_cancelled(should_cancel)
            if not is_candidate_message(message, delivered_only=config.delivered_only):
                continue
            if (
                resolve_template(
                    message,
                    compiled,
                    policy,
                    sender_case_sensitive=config.sender_case_sensitive,
                )
                is not None
            ):
                continue
            if matches_candidate_pattern(
                message,
                pattern,
                sender_keys,
                policy,
                sender_case_sensitive=config.sender_case_sensitive,
            ):
                result.append(_to_view(message))
        return tuple(result)


def _to_view(message: SmsMessage) -> MatchedMessageView:
    return MatchedMessageView(
        message_id=message.message_id,
        text=message.text,
        segments=message.segments,
        masked_recipient=mask_phone(message.recipient),
        sent_at=message.sent_at,
        operator=message.operator.value,
        delivery_status=message.delivery_status or message.send_status or UNKNOWN_STATUS,
    )


def _raise_if_cancelled(should_cancel: Callable[[], bool] | None) -> None:
    if should_cancel is not None and should_cancel():
        raise OperationCancelled("Операция отменена пользователем")
