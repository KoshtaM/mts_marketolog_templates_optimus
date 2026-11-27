export interface ImportBatch {
  id: string
  source_path: string
  source_name: string
  source_sha256: string
  kind: string
  imported_at: string | null
  row_count: number
  message_count: number
  total_cost: string
  period_from: string | null
  period_to: string | null
  status: string
  name: string | null
  period_label: string | null
  warnings: string[]
  segment_count: number
  duplicate_message_ids: number
  delivered_rows: number
  partial_delivered_rows: number
  send_error_rows: number
  delivery_error_rows: number
  empty_package_rows: number
}

export interface QualityIssue {
  message_id: string
  field: string
  detail: string
}

export interface ImportReport {
  batch: ImportBatch
  reused: boolean
  duplicate_message_ids: number
  segment_count: number
  delivered_rows: number
  partial_delivered_rows: number
  send_error_rows: number
  delivery_error_rows: number
  empty_package_rows: number
  issues: QualityIssue[]
  has_issues: boolean
}

export interface TemplateFilePreview {
  source_name: string
  upload_id: string
  columns: string[]
  sample_rows: Record<string, unknown>[]
  suggested: Record<string, string> | null
}

export interface TemplateImportReport {
  imported: number
  updated: number
  duplicates: number
  skipped_empty: number
  removed: number
  warnings: string[]
}

export interface SmsTemplate {
  template_id: string
  name: string
  text: string
  sender: string
  active: boolean
  monthly_fee: string
  operators: string[]
  traffic_type: string
  example: string
}

export interface DaySegments {
  day: string
  segments: number
}

export interface OperatorDaySegments {
  operator: string
  segments: number
}

export interface DailySegments extends DaySegments {
  operators: OperatorDaySegments[]
}

export interface BatchStatistics {
  message_count: number
  segments: number
  cost: string
  delivered: number
  ordinary_messages: number
  ordinary_segments: number
  ordinary_cost: string
  ordinary_rate: string | null
  templated_messages: number
  templated_segments: number
  templated_cost: string
  templated_rate: string | null
  senders: number
  average_cost: string
  ordinary_average_cost: string
  templated_average_cost: string
  average_segment_cost: string
  ordinary_average_segment_cost: string
  templated_average_segment_cost: string
  delivered_share: number
  ordinary_share: number
  templated_share: number
  ordinary_segment_share: number
  templated_segment_share: number
  average_segments: number
}

export interface OperatorStatistics {
  operator: string
  messages: number
  segments: number
  cost: string
  average_segment_cost: string
}

export interface CountBucket {
  segments: number
  count: number
  share: number
}

export interface SubscriberOperator {
  operator: string
  subscribers: number
  share: number
}

export interface SegmentationStatistics {
  subscribers: number
  subscriber_segments: number
  subscriber_messages: number
  average_subscriber_segments: number
  average_subscriber_messages: number
  subscribers_by_segments: CountBucket[]
  subscribers_by_operator: SubscriberOperator[]
  messages_by_segments: CountBucket[]
  zero_segment_messages: number
}

export interface DashboardSummary {
  batches: ImportBatch[]
  batch: ImportBatch | null
  statistics: BatchStatistics | null
  template_count: number
  active_templates: number
  inactive_templates: number
  candidates: number
  total_monthly_net_benefit: string
  profitable_candidates: number
  profitable_candidates_benefit: string
  loss_templates_benefit: string
  potential_benefit: string
  warnings: string[]
  operators: OperatorStatistics[]
  segmentation: SegmentationStatistics | null
  daily_segments: DailySegments[]
}

export interface DriftFragment {
  kind: 'equal' | 'removed' | 'added'
  text: string
}

export interface TemplateDrift {
  candidate_id: string
  candidate_text: string
  similarity: number
  template_fragments: DriftFragment[]
  candidate_fragments: DriftFragment[]
  removed: string[]
  added: string[]
  changed_tokens: number
  total_tokens: number
}

export interface TemplateMetrics {
  template_id: string
  name: string
  sender: string
  text: string
  operators: string[]
  active: boolean
  matched_messages: number
  matched_segments: number
  delivered_messages: number
  unique_recipients: number
  triggered_messages: number
  off_operator_messages: number
  actual_cost: string
  baseline_cost: string
  template_fee: string
  net_benefit: string
  trigger_rate: number
  monthly_messages: number
  monthly_segments: number
  monthly_actual_cost: string
  monthly_baseline_cost: string
  monthly_net_benefit: string
  share_of_all_segments: number
  share_of_templated_segments: number
  daily_segments: DaySegments[]
  drift: TemplateDrift | null
}

export interface Candidate {
  candidate_id: string
  template_text: string
  messages: number
  segments: number
  actual_cost: string
  templated_cost: string
  monthly_messages: number
  monthly_segments: number
  monthly_actual_cost: string
  monthly_templated_cost: string
  monthly_saving: string
  template_fee: string
  net_monthly: string
  payback_months: number | null
  confidence: number
  coverage: number
  senders: string[]
  operators: string[]
  period_from: string | null
  period_to: string | null
  is_partial_period: boolean
  examples: string[]
  status: string
  warnings: string[]
  foreign_matches: number
  share_of_all_segments: number
  daily_segments: DaySegments[]
}

export interface OperatorTrigger {
  template_id: string
  template_name: string
  sender: string
  operator: string
  listed: boolean
  matched_messages: number
  triggered_messages: number
  matched_segments: number
  share: number
  trigger_rate: number
}

export interface TemplateTrendPoint {
  batch_id: string
  period_from: string | null
  period_to: string | null
  segments: number
  triggered_messages: number
  trigger_rate: string
  net_benefit: string
}

export interface Deterioration {
  template_id: string
  previous_triggered_messages: number
  current_triggered_messages: number
  previous_trigger_rate: string
  current_trigger_rate: string
}

export interface TemplateTrend {
  template_id: string
  points: TemplateTrendPoint[]
  deterioration: Deterioration | null
}

export interface Analysis {
  run_id: string
  batch_id: string
  created_at: string | null
  period_from: string | null
  period_to: string | null
  message_count: number
  matched_message_count: number
  triggered_message_count: number
  total_net_benefit: string
  total_monthly_net_benefit: string
  total_segments: number
  templated_segments: number
  inactive_templates: number
  trigger_rate: number
  is_partial_period: boolean
  metrics: TemplateMetrics[]
  candidates: Candidate[]
  operator_triggers: OperatorTrigger[]
  warnings: string[]
  daily_total_segments: DaySegments[]
  daily_templated_segments: DaySegments[]
}

export interface MatchedMessage {
  message_id: string
  text: string
  segments: number
  masked_recipient: string
  sent_at: string
  operator: string
  delivery_status: string
}

export type ActionKind = 'loss_template' | 'unworking_template' | 'profitable_candidate'

export type Action = 'delete' | 'add' | 'watch'

export type ActionDrillDown = 'template'

export interface ActionItem {
  key: string
  kind: ActionKind
  severity: number
  title: string
  subject: string
  template_id: string | null
  template_name: string
  operator: string | null
  detail: string
  recommendation: string
  monthly_loss: string
  monthly_benefit: string
  messages: number
  segments: number
  drill_down: ActionDrillDown | null
  action: Action | null
}

export interface ActionCenter {
  batch_id: string
  period_from: string | null
  period_to: string | null
  is_partial_period: boolean
  monthly_factor: number
  total_monthly_loss: string
  total_monthly_benefit: string
  loss_templates: number
  profitable_candidates: number
  unmatched_templated_messages: number
  unmatched_templated_segments: number
  unmatched_templated_cost: string
  observed_ordinary_rate: string | null
  observed_templated_rate: string | null
  items: ActionItem[]
  warnings: string[]
}

export interface BenefitThresholds {
  levels: number[]
}

export interface AppSettings {
  data_dir: string
  database_path: string
  template_fee: string
  min_support: number
  min_cluster_segments: number
  min_text_length: number
  max_foreign_matches: number
  max_w_words: number
  max_d_words: number
  max_word_slots_per_merge: number
  max_literal_cardinality: number
  max_tail_depth: number
  punctuation_policy: string
  fold_yo: boolean
  fold_homoglyphs: boolean
  sender_case_sensitive: boolean
  baseline_mode: string
  delivered_only: boolean
  benefit_thresholds: string[]
  theme: string
}

export interface ThemePalette {
  window: string
  surface: string
  surface_alt: string
  text: string
  text_muted: string
  accent: string
  accent_hover: string
  accent_text: string
  border: string
  header: string
  header_text: string
  selection: string
  selection_text: string
  positive: string
  negative: string
  accent_secondary: string
  accent_pressed: string
  focus_ring: string
  warning: string
  shadow: string
}

export interface Theme {
  id: string
  name: string
  description: string
  palette: ThemePalette
  font_family: string
  font_heading: string
  font_mono: string
  font_size: number
  radius: number
  border_width: number
  spacing_scale: number
  hard_shadow: boolean
  bold_text: boolean
}
