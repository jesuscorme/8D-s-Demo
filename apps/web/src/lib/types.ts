export type Me = {
  user: { id: string; email: string; display_name: string };
  organization: { id: string; name: string };
  roles: string[];
  role_names: string[];
  permissions: string[];
};

export type User = { id: string; display_name: string; email: string };
export type Plant = { id: string; code: string; name: string };

export type Requirement = { key: string; label: string; met: boolean };
export type DisciplineStatus = "not_started" | "in_progress" | "pending_review" | "approved" | "blocked";

export type Discipline = {
  code: string;
  name: string;
  status: DisciplineStatus;
  available: boolean;
  requirements: Requirement[];
  pending_count: number;
  can_submit: boolean;
  blockers: string[];
  content?: Record<string, string | string[] | null>;
  submitted_at?: string | null;
  submitted_by_name?: string | null;
  approved_at?: string | null;
  approved_by_name?: string | null;
  review_comment?: string | null;
};

export type CaseSummary = {
  id: string;
  folio: string;
  title: string;
  status: string;
  severity: string;
  part_number: string | null;
  customer_name: string | null;
  defect_date: string | null;
  is_demo: boolean;
  updated_at: string;
  plant_code: string;
  owner_name: string | null;
  current_discipline: string | null;
};

export type Case = {
  id: string;
  folio: string;
  title: string;
  status: string;
  severity: string;
  source_type: string | null;
  problem_description: string;
  customer_name: string | null;
  product_name: string | null;
  part_number: string | null;
  process_name: string | null;
  lot_number: string | null;
  defect_date: string | null;
  detected_quantity: number | null;
  affected_quantity: number | null;
  owner_user_id: string | null;
  owner_name: string | null;
  opened_by_name: string;
  plant_id: string;
  plant_code: string;
  plant_name: string;
  cancel_reason: string | null;
  target_close_date: string | null;
  closed_at: string | null;
  is_demo: boolean;
  version: number;
  created_at: string;
  updated_at: string;
  team: { user_id: string; team_role: string; display_name: string; email: string }[];
  workflow: Discipline[];
  locked_fields: string[];
};

export type Containment = {
  id: string;
  description: string;
  location: string | null;
  responsible_user_id: string | null;
  responsible_name: string | null;
  due_date: string | null;
  status: string;
  quantity_checked: number | null;
  quantity_rejected: number | null;
  evidence_notes: string | null;
  verified_by_name: string | null;
  verified_at: string | null;
  overdue: boolean;
  attachment_count: number;
};

export type Attachment = {
  id: string;
  file_name: string;
  mime_type: string;
  file_size_bytes: number;
  sha256_hex: string;
  purpose: string;
  description: string | null;
  containment_id: string | null;
  cause_id: string | null;
  action_id: string | null;
  effectiveness_check_id: string | null;
  system_update_id: string | null;
  uploaded_at: string;
  uploaded_by_name: string;
};

export type AlertSummary = {
  id: string;
  folio: string;
  alert_number: number;
  revision: number;
  status: string;
  failure_type: string;
  title: string;
  issued_at: string | null;
  created_at: string;
  case_id: string;
  case_folio: string;
  document_id: string | null;
};

export type Alert = {
  id: string;
  folio: string;
  case_id: string;
  case_folio: string;
  case_title: string;
  alert_number: number;
  revision: number;
  status: string;
  failure_type: "internal" | "external";
  title: string;
  what_happened: string | null;
  when_happened: string | null;
  where_happened: string | null;
  who_is_affected: string | null;
  how_detected: string | null;
  affected_areas: string | null;
  affected_quantity: number | null;
  containment_summary: string | null;
  responsible_user_id: string | null;
  responsible_name: string | null;
  issued_by_name: string | null;
  issued_at: string | null;
  revision_reason: string | null;
  photos: { attachment_id: string; kind: "nok" | "ok"; file_name: string }[];
  revisions: { id: string; revision: number; status: string; issued_at: string | null; revision_reason: string | null; document_id: string | null; sha256_hex: string | null }[];
  missing_to_issue: string[];
};

export type Category = { id: string; code: string; name_es: string; name_en: string; display_order: number };

export type Idea = {
  id: string;
  category_id: string;
  category_code: string;
  title_es: string;
  title_en: string | null;
  description_es: string | null;
  process_tags: string[];
  defect_tags: string[];
  is_active: boolean;
  is_base: boolean;
  score?: number;
  reasons?: string[];
};

export type Cause = {
  id: string;
  category_id: string;
  category_code: string;
  category_name: string;
  potential_cause: string;
  parent_cause_id: string | null;
  notes: string | null;
  investigation_status: string;
  source_idea_id: string | null;
  added_by_name: string;
  validation_count: number;
  attachment_count: number;
  documented_answer: string | null;
  followed_process_answer: string | null;
  verification_method: string | null;
  evidence_summary: string | null;
  rationale: string | null;
  validated_at: string | null;
  validated_by_name: string | null;
  responsible_name: string | null;
  responsible_user_id: string | null;
  due_date: string | null;
  procedure_finding: { code: string; label: string; hint: string } | null;
};

export type Validation = {
  id: string;
  decision: string;
  documented_answer: string;
  followed_process_answer: string;
  verification_method: string | null;
  evidence_summary: string | null;
  rationale: string | null;
  validated_at: string;
  validated_by_name: string;
  responsible_name: string | null;
  due_date: string | null;
};

export type AuditEvent = {
  id: number;
  event_type: string;
  entity_type: string;
  occurred_at: string;
  actor_name: string | null;
  old_values: Record<string, unknown> | null;
  new_values: Record<string, unknown> | null;
  metadata: Record<string, unknown>;
};

export type DocumentRow = {
  id: string;
  document_type: string;
  revision: number;
  file_name: string;
  file_size_bytes: number;
  sha256_hex: string;
  status: string;
  template_version: string;
  generated_at: string;
  alert_id: string | null;
  generated_by_name: string;
};

export type Action = {
  id: string;
  case_id: string;
  action_type: "corrective" | "preventive" | "systemic";
  cause_id: string | null;
  cause_text: string | null;
  cause_status: string | null;
  description: string;
  responsible_user_id: string | null;
  responsible_name: string | null;
  due_date: string | null;
  status: string;
  implementation_evidence: string | null;
  evidence_exception: string | null;
  implemented_at: string | null;
  submitted_by: string | null;
  submitted_by_name: string | null;
  approved_by_name: string | null;
  approved_at: string | null;
  review_comment: string | null;
  cancel_reason: string | null;
  overdue: boolean;
  attachment_count: number;
  latest_effectiveness: string | null;
};

export type SystemUpdate = {
  id: string;
  update_type: string;
  document_reference: string;
  description: string | null;
  responsible_name: string | null;
  status: string;
  completed_on: string | null;
  evidence_notes: string | null;
  attachment_count: number;
};

export type Criterion = {
  id: string;
  description: string;
  metric_name: string;
  defect_unit: string;
  denominator_type: string;
  denominator_label: string | null;
  threshold_type: string;
  threshold_value: number;
  min_period_days: number;
  min_denominator: number;
  status: string;
  approved_by_name: string | null;
  approved_at: string | null;
};

export type Check = {
  id: string;
  action_id: string;
  action_description: string;
  criterion_id: string;
  period_start: string;
  period_end: string;
  denominator_quantity: number | null;
  defect_quantity: number | null;
  days_without_production: number;
  data_notes: string | null;
  computed_result: string;
  result: string;
  rationale: string | null;
  decided_by_name: string | null;
  decided_at: string | null;
  responsible_name: string | null;
  attachment_count: number;
  evaluation: { result: string; value: number | null; reasons: string[] };
  allowed_decisions: string[];
};

export type Effectiveness = { criteria: Criterion[]; checks: Check[]; denominators: Record<string, string> };

export type LessonSummary = {
  id: string;
  folio: string;
  lesson_number: number;
  revision: number;
  title: string;
  status: string;
  language_code: string;
  products: string[];
  processes: string[];
  plant_codes: string[];
  situations: string[];
  published_at: string | null;
  updated_at: string;
  source_folio: string;
  application_count: number;
};

export type Lesson = LessonSummary & {
  source_case_id: string;
  source_title: string;
  problem_summary: string;
  verified_root_cause: string;
  actions_summary: string;
  effectiveness_summary: string | null;
  before_summary: string | null;
  after_summary: string | null;
  documents_updated: string[];
  training_summary: string | null;
  revision_reason: string | null;
  review_comment: string | null;
  created_by: string;
  created_by_name: string;
  created_at: string;
  submitted_by_name: string | null;
  submitted_at: string | null;
  reviewed_by_name: string | null;
  reviewed_at: string | null;
  published_by_name: string | null;
  retired_by_name: string | null;
  retired_at: string | null;
  retire_reason: string | null;
  missing_to_submit: string[];
  photos: { attachment_id: string; kind: "before" | "after"; caption: string | null; file_name: string }[];
  revisions: { id: string; revision: number; status: string; revision_reason: string | null; published_at: string | null; created_at: string }[];
  applications: { id: string; lesson_id: string; revision: number; evaluation: string; outcome: string; application_notes: string | null; applied_at: string; target_case_id: string; target_folio: string; target_title: string; applied_by_name: string }[];
  documents: { id: string; revision: number; file_name: string; sha256_hex: string; status: string; generated_at: string }[];
};

export type IssuedDocument = { id: string; revision: number; sha256_hex: string; file_name: string; document_type: string; status: string };
