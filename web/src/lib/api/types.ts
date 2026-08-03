export interface PositionBrief {
  id: number;
  name: string;
  menu_flags: Record<string, boolean> | null;
  metrics: string[] | null;
  managed_by_roles: string[] | null;
}

export interface Position extends PositionBrief {
  is_active: boolean;
  created_at: string;
}

export interface User {
  id: number;
  telegram_id: number | null;
  full_name: string;
  role: "employee" | "hr" | "rop" | "boss" | "dasturchi";
  team_id: number | null;
  manager_id: number | null;
  position_id: number | null;
  position: PositionBrief | null;
  bot_started: boolean;
  is_active: boolean;
  is_seat: boolean;
  /** Davomat keldi/ketdi vaqtini tuzatish huquqi — Dasturchi SHAXSAN beradi
      (roldan qat'i nazar). hr/boss/dasturchi uchun ahamiyatsiz: ular baribir
      tahrirlay oladi. */
  can_edit_attendance: boolean;
  /** Joylashuvsiz check-in: GPS umuman so'ralmaydi, ofis radiusi tekshirilmaydi
      (Face ID baribir talab qilinadi). */
  skip_location_check: boolean;
  /** Kechikish/jarima qoidasini o'zgartirish huquqi — Dasturchi yoki Boshliq
      shaxsan beradi. FAQAT jarima qoidasini ochadi (oylik hisoblash/tasdiqlash
      emas). */
  can_edit_fine_policy: boolean;
  crm_external_id: string | null;
  crm_visit_external_id: string | null;
  has_face: boolean;
  created_at: string;
}

export interface RegisterFaceResult {
  status: "registered" | "pending_approval";
  user: User;
}

export interface Attendance {
  id: number;
  user_id: number;
  user_full_name: string | null;
  date: string;
  check_in_time: string | null;
  check_out_time: string | null;
  check_in_distance_m: number | null;
  late_minutes: number;
  early_leave_minutes: number;
  worked_minutes: number;
  status: "present" | "late" | "absent" | "weekend";
  is_weekend: boolean;
  note: string | null;
}

export interface ReadinessIssue {
  user_id: number;
  full_name: string;
  date: string | null;
  detail: string | null;
}

export interface AttendanceReadiness {
  date_from: string;
  date_to: string;
  ok: boolean;
  no_schedule: ReadinessIssue[];
  open_checkouts: ReadinessIssue[];
  auto_closed: ReadinessIssue[];
  pending_excused: ReadinessIssue[];
  no_face: ReadinessIssue[];
}

export interface ManualAttendancePayload {
  user_id: number;
  date: string;
  /** Mahalliy devor-soati "HH:MM"; null — tozalash */
  check_in: string | null;
  check_out: string | null;
  note?: string | null;
  reason: string;
}

export interface Office {
  id: number;
  name: string;
  latitude: number;
  longitude: number;
  radius_meters: number;
  is_active: boolean;
  created_at: string;
}

export interface AttendanceDashboard {
  today: string;
  summary: {
    total_employees: number;
    working_today: number;
    checked_in_today: number;
    present_now: number;
    late_today: number;
    left_today: number;
    not_checked_in: number;
    /** Bugun ish jadvali bo'yicha DAM OLISHDAGILAR soni. Ular
        `working_today`ga ham, `not_checked_in`ga ham kirmaydi. */
    on_day_off: number;
    month_late_minutes: number;
    month_worked_hours: number;
  };
  in_office: { user_name: string; check_in_time: string; late_minutes: number }[];
  recent: {
    user_name: string;
    check_in_time: string;
    check_out_time: string | null;
    late_minutes: number;
    status: string;
  }[];
  /** Bugun dam olishdagi xodimlar — «kelmadi» bilan aralashib ketmasligi uchun. */
  on_day_off: { user_id: number; full_name: string }[];
}

export interface EmployeeAttendanceSummary {
  user_id: number;
  full_name: string;
  present_days: number;
  late_count: number;
  late_minutes: number;
  early_minutes: number;
  worked_minutes: number;
}

export interface LateDayEntry {
  date: string;
  late_minutes: number;
}

export interface LateStatRow {
  user_id: number;
  full_name: string;
  late_days: number;
  total_late_minutes: number;
  avg_late_minutes: number;
  max_late_minutes: number;
  days: LateDayEntry[];
}

export interface Task {
  id: number;
  assigned_by: number;
  assigned_to: number;
  assigned_to_name: string;
  title: string;
  description: string | null;
  deadline: string | null;
  status: "pending" | "done" | "overdue" | "cancelled";
  completed_at: string | null;
  created_at: string;
}

export interface ExcusedDay {
  id: number;
  user_id: number;
  user_full_name: string;
  date: string;
  reason: string;
  status: "pending" | "approved" | "rejected";
  decided_by: number | null;
  decided_at: string | null;
  created_at: string;
}

export interface CrmOperatorRow {
  crm_external_id: string;
  calls_today: number;
  matched_user: User | null;
  suggested_user: User | null;
}

export interface CrmVisitOperatorRow {
  responsible_id: string;
  responsible_name: string;
  visits_today: number;
  matched_user: User | null;
  suggested_user: User | null;
}

export interface MetricProgressRow {
  key: string;
  label: string;
  value: number; // bugungi haqiqiy (CRM/qo'lda) qiymat
  norm: number | null; // belgilangan norma
  tracked: boolean; // false — ma'lumot manbai (CRM ID) yo'q, value doim 0
}

export interface TeamNormRow {
  user_id: number;
  full_name: string;
  position_name: string | null;
  can_edit: boolean;
  metrics: MetricProgressRow[];
}

export interface DailyResult {
  id: number;
  user_id: number;
  date: string;
  conversations_count: number;
  visits_count: number;
  source: "crm" | "manual";
  raw_data: Record<string, unknown> | null;
}

export interface Bonus {
  id: number;
  user_id: number;
  period: string;
  amount: number;
  calculated_at: string;
  breakdown: Record<string, unknown> | null;
}

export interface LeadStageRow {
  pipe_status_id: number;
  stage_name: string;
  count: number;
}

export interface LeadOperatorRow {
  responsible_id: number;
  responsible_name: string;
  calls: number;
  calls_in: number;
  calls_out: number;
  total: number;
  visits: number;
}

export interface LeadStageDaySummary {
  date: string;
  calls: number;
  total: number;
  visits: number;
}

export interface LeadStageMonth {
  month: string;
  calls: number;
  total: number;
  visits: number;
  days: LeadStageDaySummary[];
  last_updated: string | null;
}

export interface LeadStageDay {
  date: string;
  calls: number;
  calls_in: number;
  calls_out: number;
  total: number;
  visits: number;
  stages: LeadStageRow[];
  operators: LeadOperatorRow[];
  responsible_id: number | null;
  responsible_name: string | null;
  last_updated: string | null;
}

// --- "Statistika" paneli (faqat rahbarlar) ---

export interface StatsSeriesPoint {
  date: string;
  calls: number;
  talk_sec: number;
  leads: number;
  visits: number;
}

export interface StatsReason {
  date: string;
  hour: number;
  user_name: string;
  reason: string | null; // null — operator hali javob yozmagan
  ai_category: string | null;
  raw_text: string | null;
  verified: boolean | null; // false — faktlarga zid chiqqan
  verify_note: string | null;
}

export interface StatsOverview {
  days: number;
  date_from: string;
  date_to: string;
  series: StatsSeriesPoint[];
  reasons: StatsReason[];
}

export interface OperatorSummaryRow {
  responsible_id: number;
  name: string;
  is_system_user: boolean;
  calls: number;
  prev_calls: number | null;
  calls_pct: number | null;
  talk_sec: number;
  leads: number;
  visits: number;
  tasks_done: number | null;
  tasks_total: number | null;
}

export interface OperatorSummary {
  period: string;
  date_from: string;
  date_to: string;
  prev_from: string;
  prev_to: string;
  operators: OperatorSummaryRow[];
  totals: {
    calls: number;
    prev_calls: number | null;
    calls_pct: number | null;
    talk_sec: number;
    leads: number;
    visits: number;
  };
}

export interface WorkDayEntry {
  weekday: number; // 0=Dush ... 6=Yak
  is_working: boolean;
  start_time: string | null;
  end_time: string | null;
}

export interface WorkWeekly {
  user_id: number;
  user_full_name: string;
  days: WorkDayEntry[];
}

export interface WorkOverride {
  id: number;
  date: string;
  is_working: boolean;
  start_time: string | null;
  end_time: string | null;
  note: string | null;
}

/** Aniq sana uchun AMALDAGI jadval: override > haftalik andoza > unset
 *  (api/schemas.py: EffectiveDay). `source` nima qayerdan kelganini aytadi —
 *  xodimga "bu kun alohida o'zgartirilgan" deb ko'rsatish uchun kerak. */
export interface EffectiveDay {
  date: string;
  weekday: number; // 0=Dush ... 6=Yak
  is_working: boolean;
  start_time: string | null;
  end_time: string | null;
  source: "override" | "weekly" | "unset";
  note: string | null;
}

/** Dushanbadan boshlab 7 kun (api/schemas.py: WorkWeekOut). */
export interface WorkWeek {
  user_id: number;
  user_full_name: string;
  days: EffectiveDay[];
}

/** Xodimning oxirgi TASDIQLANGAN oylik varaqasi (api/schemas.py:
 *  BotPayslipOut). `calculated=false` — hali tasdiqlangani yo'q; qolgan
 *  maydonlar shunda null bo'ladi. Bot ham shu shaklni oladi. */
/** Bugungi natija + lavozimga moslashgan ko'rsatkichlar (api/schemas.py:
 *  DailyResultTodayOut). Bot «📊 Bugungi normam» ham shu shaklni oladi. */
export interface DailyResultToday {
  conversations_count: number;
  visits_count: number;
  metrics: MetricProgressRow[];
}

/** Xodimning shaxsiy statistikasi (api/schemas.py: MyStatsOut).
 *  `week_totals`/`month_totals` kalitlari — metrika kalitlari
 *  (suhbat/tashrif/oddiy_video/dumaloq_video), lavozimga qarab. */
export interface MyStats {
  period: string; // "YYYY-MM"
  today: MetricProgressRow[];
  week_totals: Record<string, number>;
  month_totals: Record<string, number>;
  tasks_done: number;
  tasks_total: number;
  excused_days: number;
}

/** Soatlik reja — bitta ko'rsatkich holati (api/schemas.py:
 *  HourlyMetricStatus). `delta` = actual - cumulative_target: + oldinda,
 *  - orqada. `tracked=false` bo'lsa actual/delta ma'nosiz. */
export interface HourlyMetricStatus {
  key: string;
  label: string;
  norm: number; // kunlik nominal norma
  effective_norm: number; // bugungi ish soatiga moslashtirilgan
  per_hour: number;
  this_hour_target: number;
  cumulative_target: number; // shu paytgacha bo'lishi kerak
  actual: number;
  delta: number;
  tracked: boolean;
}

/** api/schemas.py: HourlyPlanOut. `text` — botga tayyor HTML; web uni
 *  ISHLATMAYDI, strukturali maydonlardan o'zi chizadi. */
export interface HourlyPlan {
  date: string;
  is_working: boolean;
  in_lunch: boolean;
  start_time: string | null;
  end_time: string | null;
  now: string | null; // "HH:MM"
  metrics: HourlyMetricStatus[];
  text: string;
}

export interface MyPayslip {
  calculated: boolean;
  period: string | null;
  base_amount: number | null;
  fine_amount: number | null;
  absent_deduction: number | null;
  overtime_amount: number | null;
  bonus_amount: number | null;
  net: number | null;
  currency: string | null;
  approved_at: string | null;
}

// ─── Payroll (oylik ish haqi + kechikish jarimasi + qo'shimcha ish) ───

export interface FinePolicy {
  id: number;
  scope: "global" | "position" | "user";
  scope_id: number | null;
  scope_label: string | null;
  grace_minutes: number | null;
  free_late_minutes_per_month: number | null;
  fine_mode: string;
  fine_per_day: number | null;
  absent_mode: string;
  absent_fine: number | null;
  early_leave_enabled: boolean;
  early_leave_per_minute: number | null;
  monthly_cap_percent: number | null;
  monthly_cap_amount: number | null;
  fine_applies_to: "bonus_first" | "net_salary";
  is_active: boolean;
  updated_at: string;
}

export interface FinePolicyInput {
  scope: "global" | "position" | "user";
  scope_id?: number | null;
  grace_minutes?: number | null;
  free_late_minutes_per_month: number;
  fine_mode?: string;
  fine_per_day?: number | null;
  absent_mode?: string;
  absent_fine?: number | null;
  early_leave_enabled?: boolean;
  early_leave_per_minute?: number | null;
  monthly_cap_percent?: number | null;
  monthly_cap_amount?: number | null;
  fine_applies_to?: "bonus_first" | "net_salary";
  is_active?: boolean;
}

export interface SalaryRate {
  id: number;
  user_id: number;
  amount: number;
  pay_basis: "monthly" | "daily" | "hourly";
  effective_from: string;
  changed_by: number;
  note: string | null;
  created_at: string;
}

export interface OvertimeProfile {
  user_id: number;
  user_full_name: string | null;
  enabled: boolean;
  mode: "derived" | "fixed_rate";
  fixed_rate_per_hour: number | null;
  multiplier: number | null;
  norm_hours_source: "schedule" | "fixed";
  fixed_norm_hours_per_month: number | null;
  min_minutes: number;
  daily_cap_minutes: number | null;
  monthly_cap_minutes: number | null;
  updated_at: string;
}

export interface OvertimeProfileInput {
  enabled: boolean;
  mode: "derived" | "fixed_rate";
  fixed_rate_per_hour?: number | null;
  multiplier?: number | null;
  norm_hours_source: "schedule" | "fixed";
  fixed_norm_hours_per_month?: number | null;
  min_minutes: number;
  daily_cap_minutes?: number | null;
  monthly_cap_minutes?: number | null;
}

export interface OvertimeEntry {
  id: number;
  user_id: number;
  user_full_name: string | null;
  date: string;
  minutes: number;
  source: "auto_attendance" | "manual";
  status: "pending" | "approved" | "rejected";
  note: string | null;
  decided_by: number | null;
  decided_at: string | null;
  created_at: string;
}

export interface PayrollAdjustment {
  id: number;
  user_id: number;
  period: string;
  kind: "plus" | "minus";
  amount: number;
  reason: string;
  created_by: number;
  created_at: string;
}

export interface PayslipItem {
  kind: string;
  label: string;
  quantity: number | null;
  rate: number | null;
  amount: number;
  sort_order: number;
}

export interface PayslipRow {
  user_id: number;
  full_name: string;
  status: string;
  base_amount: number;
  late_days: number;
  fined_late_days: number;
  fine_amount: number;
  absent_days: number;
  absent_deduction: number;
  overtime_minutes: number;
  overtime_amount: number;
  bonus_amount: number;
  gross: number;
  net: number;
}

export interface PayslipDetail {
  id: number;
  user_id: number;
  full_name: string;
  period: string;
  status: string;
  base_amount: number;
  pay_basis: string;
  rate_snapshot: number | null;
  scheduled_days: number;
  worked_days: number;
  absent_days: number;
  excused_days: number;
  scheduled_minutes: number;
  worked_minutes: number;
  late_days: number;
  late_minutes: number;
  fined_late_days: number;
  fined_late_minutes: number;
  fine_amount: number;
  absent_deduction: number;
  overtime_minutes: number;
  overtime_amount: number;
  overtime_rate_snapshot: number | null;
  bonus_amount: number;
  adjustments_plus: number;
  adjustments_minus: number;
  gross: number;
  net: number;
  currency: string;
  calculated_at: string | null;
  approved_at: string | null;
  items: PayslipItem[];
  breakdown: Record<string, unknown> | null;
}

export interface PayrollPeriodSummary {
  period: string;
  status: string;
  locked: boolean;
  calculated_at: string | null;
  approved_at: string | null;
  employee_count: number;
  total_net: number;
}

export interface PayrollPreflight {
  period: string;
  ok: boolean;
  attendance: AttendanceReadiness;
  no_salary_rate: ReadinessIssue[];
  pending_overtime: ReadinessIssue[];
}

export interface PayrollLateStatus {
  period: string;
  free_limit_minutes: number | null;
  used_minutes: number;
  remaining_minutes: number | null;
  fined_days_so_far: number;
  fine_per_day: number | null;
}

export interface AuditLog {
  id: number;
  actor_id: number | null;
  actor_name: string | null;
  action: string;
  target_user_id: number | null;
  target_name: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  created_at: string;
}

// ─── Dasturchi rejimi (super-admin, OYLIK_JARIMA_REJASI.md 11-bo'lim) ───
// `/admin/records/{entity}` universal ustki qatlamdir — server tomonida har
// entity o'zining ustunlariga ega (SQLAlchemy jadval ustunlari to'g'ridan-
// to'g'ri JSON'ga aylantiriladi), shuning uchun bitta qat'iy interfeys
// o'rniga umumiy record turi ishlatiladi.
export type AdminRecord = Record<string, unknown>;

export interface OverrideAuditRow {
  id: number;
  actor_id: number | null;
  action: string;
  target_user_id: number | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  created_at: string;
}

/** Davomat vaqtini tuzatish huquqi SHAXSAN berilgan odam. */
export interface AttendanceEditorRow {
  id: number;
  full_name: string;
  role: string;
  is_active: boolean;
}

/** Joylashuvsiz («bez lokatsiya») check-in ruxsati berilgan odam —
    `AttendanceEditorRow` bilan bir xil shakl, lekin boshqa ma'no. */
export type LocationExemptRow = AttendanceEditorRow;

/** Sababsiz kelmagan kun uchun tushuntirish xati. */
export interface ExplanationRequestRow {
  id: number;
  user_id: number;
  user_full_name: string | null;
  date: string;
  /** pending — so'raldi; answered — xodim yozdi; accepted/rejected — HR qarori. */
  status: "pending" | "answered" | "accepted" | "rejected";
  asked_at: string | null;
  answer_text: string | null;
  answered_at: string | null;
  decided_by: number | null;
  decided_at: string | null;
  decision_note: string | null;
}
