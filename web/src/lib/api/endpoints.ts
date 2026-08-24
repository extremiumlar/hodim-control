import { apiFetch, apiUpload, ApiError, API_BASE_URL, getToken, UNAUTHORIZED_EVENT } from "./client";
import type {
  AdminRecord,
  AdvanceAnnouncement,
  AdvanceDaySummary,
  AdvanceLimit,
  AdvanceSettings,
  AdvanceSettingsInput,
  MyAdvances,
  Appeal,
  AppealDecideResult,
  Attendance,
  EmployeeRequest,
  AckPending,
  AckReader,
  AnnouncementItem,
  CourseAssignmentRow,
  CourseProgress,
  CourseResultOut,
  CourseDetail,
  CourseItem,
  CompanyProfileOut,
  CourseReport,
  JobDescriptionVersion,
  OrgChart,
  OrgMyPlace,
  OrgPositionDetail,
  MyCourseItem,
  HrFrequentReport,
  HrInquiryItem,
  HrSuggestion,
  MyProfile,
  ProbationItem,
  ProfileChange,
  StaffItem,
  StaffSummary,
  AssetHistoryItem,
  AssetItem,
  CertificateItem,
  DeadlineItem,
  DocumentTemplate,
  DeadlineKind,
  EmployeeDocument,
  Offer,
  Holiday,
  LeaveBalance,
  RequestCalc,
  RequestDecideResult,
  RequestInterruptResult,
  RequestRevokeResult,
  AttendanceDashboard,
  AttendanceMatrix,
  AttendanceReadiness,
  FaceReregRequest,
  MyAttendanceHistory,
  AuditLog,
  CelebrationMediaRow,
  Economics,
  TargetPlan,
  FunnelAnalysis,
  FunnelRules,
  OperatorQuality,
  TargetProgress,
  TargetSplit,
  FunnelChannels,
  FunnelData,
  FunnelMonths,
  Bonus,
  DailyResult,
  EmployeeAttendanceSummary,
  ExcusedDay,
  FinePolicy,
  FinePolicyInput,
  LateStatRow,
  ManualAttendancePayload,
  MeSection,
  SetupItem,
  CrmOperatorRow,
  CrmVisitOperatorRow,
  LeadStageDay,
  LeadStageMonth,
  Office,
  OperatorSummary,
  AttendanceEditorRow,
  ExplanationRequestRow,
  LocationExemptRow,
  OverrideAuditRow,
  PushSettingsOut,
  OvertimeEntry,
  OvertimeProfile,
  OvertimeProfileInput,
  PayrollAdjustment,
  PayrollCalcStatus,
  PayrollLateStatus,
  PayrollPeriodSummary,
  PayrollPreflight,
  PayslipDetail,
  PayslipRow,
  Position,
  RegisterFaceResult,
  WorkLogCoverage,
  WorkLogEntry,
  WorkLogMonth,
  KpiRate,
  SalaryRate,
  StatsOverview,
  Task,
  TeamNormRow,
  User,
  WorkDayEntry,
  WorkOverride,
  DailyResultToday,
  HourlyPlan,
  MyPayslip,
  MyStats,
  WorkWeek,
  WorkWeekly,
} from "./types";

export const api = {
  me: () => apiFetch<User>("/users/me"),
  // Menyu — serverdan (TZ 2.6). Mijozda ro'yxat qattiq yozilmaydi.
  mySections: () => apiFetch<MeSection[]>("/me/sections"),
  setupStatus: () => apiFetch<SetupItem[]>("/me/setup-status"),

  // ── Bayramlar (TZ 2.9 / S-09) ──
  holidays: (year?: number) =>
    apiFetch<Holiday[]>(`/holidays${year ? `?year=${year}` : ""}`),
  addHoliday: (body: { date: string; name: string; kind: string }) =>
    apiFetch<Holiday>("/holidays", { method: "POST", body: JSON.stringify(body) }),
  addHolidaysBulk: (body: {
    items: { date: string; name: string; kind: string }[];
    overwrite?: boolean;
  }) =>
    apiFetch<{ added: number; updated: number; skipped: number }>("/holidays/bulk", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deleteHoliday: (id: number) =>
    apiFetch<{ ok: boolean }>(`/holidays/${id}`, { method: "DELETE" }),

  // ── Kadr hujjatlari (TZ 3.4 / S-10) ──
  myDocuments: () => apiFetch<EmployeeDocument[]>("/employee-documents/me"),
  userDocuments: (userId: number) =>
    apiFetch<EmployeeDocument[]>(`/employee-documents/user/${userId}`),
  deleteDocument: (id: number) =>
    apiFetch<{ ok: boolean }>(`/employee-documents/${id}`, { method: "DELETE" }),

  // ── Muddatlar (TZ 3.5 / S-12) ──
  deadlines: (days?: number) =>
    apiFetch<DeadlineItem[]>(`/deadlines${days ? `?days=${days}` : ""}`),
  deadlineKinds: () => apiFetch<DeadlineKind[]>("/deadlines/kinds"),
  addDeadline: (body: {
    user_id: number;
    kind: string;
    due_date: string;
    note?: string | null;
  }) => apiFetch<{ id: number }>("/deadlines", { method: "POST", body: JSON.stringify(body) }),
  closeDeadline: (body: { key: string }) =>
    apiFetch<{ ok: boolean }>("/deadlines/close", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  // ── Hujjat shablonlari va ish takliflari (TZ 3.3 / S-14, S-15) ──
  documentTemplates: () => apiFetch<DocumentTemplate[]>("/document-templates"),
  certificates: (userId?: number) =>
    apiFetch<CertificateItem[]>(
      `/certificates${userId ? `?user_id=${userId}` : ""}`
    ),
  // ── Mol-mulk (TZ 3.11 / S-18) ──
  assets: (freeOnly = false) =>
    apiFetch<AssetItem[]>(`/assets${freeOnly ? "?free_only=true" : ""}`),
  assetKinds: () =>
    apiFetch<{
      kinds: { value: string; label: string }[];
      conditions: { value: string; label: string }[];
    }>("/assets/kinds"),
  addAsset: (body: {
    inventory_no: string;
    name: string;
    kind: string;
    value?: number | null;
  }) => apiFetch<AssetItem>("/assets", { method: "POST", body: JSON.stringify(body) }),
  assignAsset: (body: { id: number; user_id: number; condition_out: string }) =>
    apiFetch<AssetItem>(`/assets/${body.id}/assign`, {
      method: "POST",
      body: JSON.stringify({ user_id: body.user_id, condition_out: body.condition_out }),
    }),
  returnAsset: (body: { id: number; condition_in: string }) =>
    apiFetch<AssetItem>(`/assets/${body.id}/return`, {
      method: "POST",
      body: JSON.stringify({ condition_in: body.condition_in }),
    }),
  assetHistory: (id: number) =>
    apiFetch<AssetHistoryItem[]>(`/assets/${id}/history`),
  myAssets: () => apiFetch<AssetItem[]>("/assets/me"),

  // ── E'lonlar va «Tanishdim» (TZ 3.12 / S-20, S-21) ──
  // ── Shtat jadvali (TZ 3.20 / S-23) ──
  // ── Sinov muddati (TZ 3.24 / S-24) ──
  // ── Profil o'zgartirish so'rovlari (TZ 3.26 / S-26) ──
  profileFields: () =>
    apiFetch<{ value: string; label: string; sensitive: boolean }[]>(
      "/profile-changes/fields"
    ),
  myProfile: () => apiFetch<MyProfile>("/profile-changes/me/profile"),
  myProfileChanges: () => apiFetch<ProfileChange[]>("/profile-changes/me"),
  requestProfileChange: (body: { field: string; new_value: string }) =>
    apiFetch<ProfileChange>("/profile-changes/me", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  profileChanges: (pendingOnly: boolean) =>
    apiFetch<ProfileChange[]>(`/profile-changes?pending_only=${pendingOnly}`),
  decideProfileChange: (body: { id: number; approve: boolean; note: string | null }) =>
    apiFetch<ProfileChange>(`/profile-changes/${body.id}/decide`, {
      method: "POST",
      body: JSON.stringify({ approve: body.approve, note: body.note }),
    }),

  probation: () => apiFetch<ProbationItem[]>("/probation"),
  probationSummary: () =>
    apiFetch<{
      total: number;
      overdue: number;
      ending_soon: number;
      default_days: number;
    }>("/probation/summary"),

  staff: () => apiFetch<StaffItem[]>("/staff"),
  staffSummary: () => apiFetch<StaffSummary>("/staff/summary"),
  addStaff: (body: {
    department: string;
    position_id: number;
    units: number;
    salary_min: number | null;
    salary_max: number | null;
  }) => apiFetch<StaffItem>("/staff", { method: "POST", body: JSON.stringify(body) }),
  closeStaff: (id: number) =>
    apiFetch<{ ok: boolean }>(`/staff/${id}`, { method: "DELETE" }),

  myAnnouncements: () => apiFetch<AnnouncementItem[]>("/announcements/me"),
  announcements: () => apiFetch<AnnouncementItem[]>("/announcements"),
  announcementQuota: () =>
    apiFetch<{ daily_limit: number; sent_today: number; left: number }>(
      "/announcements/quota"
    ),
  addAnnouncement: (body: {
    title: string;
    body: string;
    audience: string;
    scope_ids: (string | number)[] | null;
    important: boolean;
  }) =>
    apiFetch<{
      id: number;
      audience_size: number;
      ack_requested: boolean;
      left_today: number;
    }>("/announcements", { method: "POST", body: JSON.stringify(body) }),
  deleteAnnouncement: (id: number) =>
    apiFetch<{ ok: boolean }>(`/announcements/${id}`, { method: "DELETE" }),
  myAcks: () => apiFetch<AckPending[]>("/acks/me"),
  acknowledge: (body: { object_type: string; object_id: number; version: number }) =>
    apiFetch<{ ok: boolean; acknowledged_at: string }>("/acks/me/ack", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  ackReaders: (objectType: string, objectId: number, version?: number) =>
    apiFetch<AckReader[]>(
      `/acks/object/${objectType}/${objectId}${version ? `?version=${version}` : ""}`
    ),
  acceptAsset: (id: number) =>
    apiFetch<{ ok: boolean; accepted_at: string }>(`/assets/${id}/accept`, {
      method: "POST",
    }),
  assetAct: (body: { id: number; template_id: number; action: "out" | "in" }) =>
    apiFetch<{ job_id: number; missing: string[] }>(`/assets/${body.id}/act`, {
      method: "POST",
      body: JSON.stringify({ template_id: body.template_id, action: body.action }),
    }),
  assetStandardSet: (positionId: number) =>
    apiFetch<{
      position_id: number;
      items: { kind: string; kind_label: string; quantity: number; note: string | null }[];
    }>(`/assets/standard-set/${positionId}`),
  setAssetStandardSet: (body: { position_id: number; items: Record<string, number> }) =>
    apiFetch<{ ok: boolean; count: number }>("/assets/standard-set", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  assetChecklist: (userId: number) =>
    apiFetch<{
      user_id: number;
      has_position: boolean;
      items: {
        kind: string;
        kind_label: string;
        required: number;
        held: number;
        missing: number;
      }[];
    }>(`/assets/checklist/${userId}`),

  certificatePurposes: () =>
    apiFetch<{ value: string; label: string }[]>("/certificates/purposes"),
  issueCertificate: (body: {
    user_id: number;
    purpose: string;
    include_salary: boolean;
  }) =>
    apiFetch<{ id: number; number: string; queued: boolean; note: string | null }>(
      "/certificates",
      { method: "POST", body: JSON.stringify(body) }
    ),
  offers: (q?: string) =>
    apiFetch<Offer[]>(`/offers${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  addOffer: (body: {
    candidate_name: string;
    phone?: string | null;
    position_id?: number | null;
    position_text?: string | null;
    salary: number;
    probation_months?: number | null;
    start_date?: string | null;
    manager_id?: number | null;
  }) => apiFetch<Offer>("/offers", { method: "POST", body: JSON.stringify(body) }),
  setOfferStatus: (body: { id: number; status: string }) =>
    apiFetch<Offer>(`/offers/${body.id}/status`, {
      method: "PUT",
      body: JSON.stringify({ status: body.status }),
    }),
  hireFromOffer: (id: number) =>
    apiFetch<{
      user_id: number;
      full_name: string;
      created: boolean;
      salary_rate_from: string;
      onboarding_ready: boolean;
    }>(`/offers/${id}/hire`, { method: "POST" }),
  generateOfferDoc: (body: { id: number; template_id: number }) =>
    apiFetch<{ job_id: number; missing: string[] }>(`/offers/${body.id}/generate`, {
      method: "POST",
      body: JSON.stringify({ template_id: body.template_id }),
    }),
  // --- Davomat (kelib-ketish) ---
  myAttendanceToday: () => apiFetch<Attendance | null>("/attendance/me/today"),
  myCheckIn: (data: { latitude: number; longitude: number; face_descriptor: number[]; liveness: number; accuracy?: number | null }) =>
    apiFetch<Attendance>("/attendance/me/check-in", { method: "POST", body: JSON.stringify(data) }),
  myCheckOut: (data: { latitude: number; longitude: number; face_descriptor: number[]; liveness: number; accuracy?: number | null }) =>
    apiFetch<Attendance>("/attendance/me/check-out", { method: "POST", body: JSON.stringify(data) }),
  registerMyFace: (faceDescriptor: number[]) =>
    apiFetch<RegisterFaceResult>("/attendance/me/register-face", {
      method: "POST",
      body: JSON.stringify({ face_descriptor: faceDescriptor }),
    }),
  attendanceDashboard: () => apiFetch<AttendanceDashboard>("/attendance/dashboard"),
  listAttendance: (params: { user_id?: number; date_from?: string; date_to?: string; status_filter?: string } = {}) => {
    const q = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== "") as [string, string][]
    ).toString();
    return apiFetch<Attendance[]>(`/attendance${q ? `?${q}` : ""}`);
  },
  // UX-A4: `days` oynasi YOKI aniq davr (kalendar oy) — ikkalasiga bitta imzo.
  attendanceEmployeeSummary: (period: { days?: number; date_from?: string; date_to?: string } = {}) => {
    const q = new URLSearchParams(
      Object.entries(period).filter(([, v]) => v !== undefined && v !== "") as [string, string][]
    ).toString();
    return apiFetch<EmployeeAttendanceSummary[]>(`/attendance/employee-summary${q ? `?${q}` : ""}`);
  },
  attendanceLateStats: (period: { days?: number; date_from?: string; date_to?: string } = {}) => {
    const q = new URLSearchParams(
      Object.entries(period).filter(([, v]) => v !== undefined && v !== "") as [string, string][]
    ).toString();
    return apiFetch<LateStatRow[]>(`/attendance/late-stats${q ? `?${q}` : ""}`);
  },
  // UX-A2: oylik matritsa (rahbar). `userId` — bitta xodim (profil sahifasi).
  attendanceMatrix: (month?: string, userId?: number) => {
    const q = new URLSearchParams();
    if (month) q.set("month", month);
    if (userId != null) q.set("user_id", String(userId));
    const s = q.toString();
    return apiFetch<AttendanceMatrix>(`/attendance/matrix${s ? `?${s}` : ""}`);
  },
  // UX-A3: xodimning O'Z oylik tarixi.
  myAttendanceHistory: (month?: string) =>
    apiFetch<MyAttendanceHistory>(`/attendance/me/history${month ? `?month=${month}` : ""}`),
  // UX-A5: kelmagan xodimga bot/push eslatma (kuniga 2 ta limit).
  remindAttendance: (userId: number) =>
    apiFetch<{ sent: boolean; sent_today: number }>(`/attendance/remind/${userId}`, {
      method: "POST",
    }),
  // UX2-W1 (A12): bugun kelmagan BARCHAGA bitta bosishda eslatma.
  remindAllAttendance: () =>
    apiFetch<{ total: number; sent: number; failed: { full_name: string; reason: string }[] }>(
      "/attendance/remind-all",
      { method: "POST" }
    ),
  // UX-A6: yuz qayta-ro'yxat so'rovlari (web).
  listFaceRereg: (statusFilter?: string) =>
    apiFetch<FaceReregRequest[]>(
      `/attendance/face-reregistration${statusFilter ? `?status_filter=${statusFilter}` : ""}`
    ),
  decideFaceReregWeb: (itemId: number, decision: "approved" | "rejected") =>
    apiFetch<FaceReregRequest>(`/attendance/face-reregistration/${itemId}/decide-web`, {
      method: "POST",
      body: JSON.stringify({ decision }),
    }),
  deleteAttendance: (attendanceId: number) =>
    apiFetch<{ deleted: boolean }>(`/attendance/${attendanceId}`, { method: "DELETE" }),
  // HR/Boshliq (va shaxsan ruxsat berilganlar) qo'lda tuzatishi — Face ID/GPS
  // ishlamay qolgan yoki xodim bosishni unutgan kunlar uchun. Audit yoziladi.
  manualAttendance: (data: ManualAttendancePayload) =>
    apiFetch<Attendance>("/attendance/manual", { method: "PUT", body: JSON.stringify(data) }),
  // Dasturchi varianti — AUDITSIZ va jim (egasining aniq talabi). Sabab
  // so'ralmaydi, chunki hech qayerga yozilmaydi.
  adminManualAttendance: (data: ManualAttendancePayload) =>
    apiFetch<{ id: number; created: boolean; audited: boolean }>("/admin/attendance/manual", {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  attendanceReadiness: (params: { date_from?: string; date_to?: string } = {}) => {
    const q = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== "") as [string, string][]
    ).toString();
    return apiFetch<AttendanceReadiness>(`/attendance/readiness${q ? `?${q}` : ""}`);
  },
  listOffices: () => apiFetch<Office[]>("/attendance/offices"),
  createOffice: (data: { name: string; latitude: number; longitude: number; radius_meters: number; is_active: boolean }) =>
    apiFetch<Office>("/attendance/offices", { method: "POST", body: JSON.stringify(data) }),
  updateOffice: (officeId: number, data: Partial<Omit<Office, "id" | "created_at">>) =>
    apiFetch<Office>(`/attendance/offices/${officeId}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteOffice: (officeId: number) =>
    apiFetch<{ deleted: boolean }>(`/attendance/offices/${officeId}`, { method: "DELETE" }),
  getUser: (userId: number) => apiFetch<User>(`/users/${userId}`),
  listUsers: (role?: string, includeInactive = false) => {
    const params = new URLSearchParams();
    if (role) params.set("role", role);
    if (includeInactive) params.set("include_inactive", "true");
    const query = params.toString();
    return apiFetch<User[]>(`/users${query ? `?${query}` : ""}`);
  },
  createUser: (data: {
    full_name: string;
    role: string;
    team_id?: number | null;
    manager_id?: number | null;
    crm_external_id?: string | null;
    is_seat?: boolean;
    hire_date?: string | null;
  }) =>
    apiFetch<{ user: User; invite_link: string }>("/users", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  // Ishga kirgan sanani to'g'rilash — migratsiya uni stavka sanasidan
  // TAXMINAN to'ldirgan, ya'ni tuzatish yo'li kerak.
  updateHireDate: (userId: number, hireDate: string | null) =>
    apiFetch<User>(`/users/${userId}/hire-date`, {
      method: "PATCH",
      body: JSON.stringify({ hire_date: hireDate }),
    }),
  inviteLink: (userId: number) =>
    apiFetch<{ invite_link: string | null; already_started: boolean }>(`/users/${userId}/invite-link`),
  updateCrmExternalId: (userId: number, crmExternalId: string | null) =>
    apiFetch<User>(`/users/${userId}/crm-external-id`, {
      method: "PATCH",
      body: JSON.stringify({ crm_external_id: crmExternalId }),
    }),
  updateCrmVisitExternalId: (userId: number, crmVisitExternalId: string | null) =>
    apiFetch<User>(`/users/${userId}/crm-external-id`, {
      method: "PATCH",
      body: JSON.stringify({ crm_visit_external_id: crmVisitExternalId }),
    }),
  updateRole: (userId: number, role: string) =>
    apiFetch<User>(`/users/${userId}/role`, { method: "PATCH", body: JSON.stringify({ role }) }),
  updateUserPosition: (userId: number, positionId: number | null) =>
    apiFetch<User>(`/users/${userId}/position`, {
      method: "PATCH",
      body: JSON.stringify({ position_id: positionId }),
    }),
  updateUserSeat: (userId: number, isSeat: boolean) =>
    apiFetch<User>(`/users/${userId}/seat`, {
      method: "PATCH",
      body: JSON.stringify({ is_seat: isSeat }),
    }),
  // Issiq lid taqsimoti: operatorni yoqish/o'chirish (2026-08-06)
  updateUserHotLead: (userId: number, enabled: boolean) =>
    apiFetch<User>(`/users/${userId}/hot-lead`, {
      method: "PATCH",
      body: JSON.stringify({ hot_lead_enabled: enabled }),
    }),
  listPositions: (includeInactive = false) =>
    apiFetch<Position[]>(`/positions${includeInactive ? "?include_inactive=true" : ""}`),
  createPosition: (data: {
    name: string;
    menu_flags?: Record<string, boolean> | null;
    metrics?: string[] | null;
    managed_by_roles?: string[] | null;
  }) => apiFetch<Position>("/positions", { method: "POST", body: JSON.stringify(data) }),
  updatePosition: (
    positionId: number,
    data: {
      name?: string;
      menu_flags?: Record<string, boolean> | null;
      metrics?: string[] | null;
      managed_by_roles?: string[] | null;
      is_active?: boolean;
    }
  ) => apiFetch<Position>(`/positions/${positionId}`, { method: "PATCH", body: JSON.stringify(data) }),
  createBulkTasks: (data: {
    target_type: "all_employees" | "role" | "position";
    target_roles?: string[] | null;
    position_id?: number | null;
    title: string;
    description?: string;
    deadline?: string | null;
  }) => apiFetch<{ created: number }>("/tasks/bulk", { method: "POST", body: JSON.stringify(data) }),
  deleteUser: (userId: number) => apiFetch<{ deleted: boolean }>(`/users/${userId}`, { method: "DELETE" }),
  listCrmOperators: () => apiFetch<CrmOperatorRow[]>("/users/crm-operators"),
  listCrmVisitOperators: () => apiFetch<CrmVisitOperatorRow[]>("/users/crm-visit-operators"),
  deactivateUser: (userId: number) => apiFetch<User>(`/users/${userId}/deactivate`, { method: "POST" }),
  activateUser: (userId: number) => apiFetch<User>(`/users/${userId}/activate`, { method: "POST" }),
  resetAccount: (userId: number) =>
    apiFetch<{ user: User; invite_link: string }>(`/users/${userId}/reset-account`, { method: "POST" }),
  listTasks: (dateFilter = "today") => apiFetch<Task[]>(`/tasks?date_filter=${dateFilter}`),
  createTask: (data: { assigned_to: number; title: string; description?: string; deadline?: string | null }) =>
    apiFetch<Task>("/tasks", { method: "POST", body: JSON.stringify(data) }),
  cancelTask: (taskId: number) => apiFetch<Task>(`/tasks/${taskId}/cancel`, { method: "POST" }),
  deleteTask: (taskId: number) => apiFetch<{ deleted: boolean }>(`/tasks/${taskId}`, { method: "DELETE" }),
  listExcusedDays: (statusFilter?: string) =>
    apiFetch<ExcusedDay[]>(`/excused-days${statusFilter ? `?status_filter=${statusFilter}` : ""}`),
  // HR/Boshliq/Dasturchi boshqa xodim NOMIDAN sababli kunni to'g'ridan-to'g'ri
  // BELGILAYDI (so'rov emas, darhol tasdiqlangan holda yoziladi).
  // Sababli kunni saytdan tasdiqlash/rad etish. Ilgari bu FAQAT botda edi —
  // push bosilganda oqim uzilib qolardi (2026-07-31).
  decideExcusedDay: (itemId: number, data: { decision: "approved" | "rejected" }) =>
    apiFetch<ExcusedDay>(`/excused-days/${itemId}/decide/me`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  recordExcusedDayForUser: (data: {
    user_id: number;
    reason: string;
    date?: string;
    /** Berilmasa `true` — tizimning avvalgi xatti-harakati saqlanadi. */
    is_paid?: boolean;
  }) =>
    apiFetch<ExcusedDay>("/excused-days/for-user", { method: "POST", body: JSON.stringify(data) }),
  teamNorms: () => apiFetch<TeamNormRow[]>("/norms/team"),
  updateNorm: (data: { user_id: number; metric_type: string; value: number }) =>
    apiFetch<unknown>("/norms", { method: "POST", body: JSON.stringify(data) }),
  devLogin: (telegramId: number) =>
    apiFetch<{ access_token: string; user: User }>("/auth/dev-login", {
      method: "POST",
      body: JSON.stringify({ telegram_id: telegramId }),
    }),
  telegramLogin: (data: Record<string, string | number>) =>
    apiFetch<{ access_token: string; user: User }>("/auth/telegram-login", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  // Bot orqali kirish (deep-link) — Telegram Login Widget'ga ZAXIRA.
  // Widget telegram.org'dan skript yuklaydi; u bloklansa yoki sekinlashsa
  // saytga HECH KIM kira olmasdi. Bu yo'lda faqat BOT kerak: xodim botda
  // tasdiqlaydi, sayt poll qilib tokenni oladi. Mexanizm mobil ilovada
  // allaqachon ishlaydi (mobile/app/login.tsx) — endpointlar bir xil.
  // `client: "web"` — kod sayt sahifasida KO'RSATILMAYDI: bot ochilganda
  // server uni foydalanuvchining mobil ilovasiga push bilan yuboradi.
  // `pairing_code` baribir qaytadi — push qurilma topilmasa (poll'dagi
  // `code_delivery` "screen"ga tushsa) sahifa uni zaxira sifatida ko'rsatadi.
  appLoginStart: () =>
    apiFetch<{ login_token: string; deep_link: string; expires_at: string; pairing_code: string }>(
      "/auth/app-login/start",
      { method: "POST", body: JSON.stringify({ client: "web" }) }
    ),
  appLoginPoll: (loginToken: string) =>
    apiFetch<{
      status: "pending" | "confirmed" | "expired";
      token: { access_token: string; user: User } | null;
      code_delivery: "screen" | "push" | null;
    }>(
      "/auth/app-login/poll",
      { method: "POST", body: JSON.stringify({ login_token: loginToken }) }
    ),
  listDailyResults: (userId: number) => apiFetch<DailyResult[]>(`/daily-results?user_id=${userId}`),
  createManualDailyResult: (data: {
    user_id: number;
    date: string;
    conversations_count: number;
    visits_count: number;
  }) => apiFetch<DailyResult>("/daily-results/manual", { method: "POST", body: JSON.stringify(data) }),
  setManualMobilografVideos: (data: {
    user_id: number;
    date: string;
    metric_type: "oddiy_video" | "dumaloq_video";
    confirmed_count: number;
  }) =>
    apiFetch<{ user_id: number; date: string; metric_type: string; confirmed_count: number }>(
      "/mobilograf-videos/manual",
      { method: "POST", body: JSON.stringify(data) }
    ),
  listBonuses: (userId: number) => apiFetch<Bonus[]>(`/bonuses?user_id=${userId}`),
  leadStageMonth: (month?: string) =>
    apiFetch<LeadStageMonth>(`/stats/web/lead-stages${month ? `?month=${month}` : ""}`),
  leadStageDay: (day: string, responsibleId?: number) =>
    apiFetch<LeadStageDay>(
      `/stats/web/lead-stages/day/${day}${responsibleId != null ? `?responsible_id=${responsibleId}` : ""}`
    ),
  myLeadStageMonth: (month?: string) =>
    apiFetch<LeadStageMonth>(`/stats/web/lead-stages/me${month ? `?month=${month}` : ""}`),
  myLeadStageDay: (day: string) => apiFetch<LeadStageDay>(`/stats/web/lead-stages/me/day/${day}`),
  statsOverview: (days = 30, month?: string) =>
    apiFetch<StatsOverview>(`/stats/web/overview?days=${days}${month ? `&month=${month}` : ""}`),
  operatorSummary: (period: string, month?: string) =>
    apiFetch<OperatorSummary>(
      month ? `/stats/web/operator-summary?month=${month}` : `/stats/web/operator-summary?period=${period}`
    ),
  getWeeklySchedule: (userId: number) => apiFetch<WorkWeekly>(`/work-schedule/${userId}/weekly`),
  // UX-A7: barcha kuzatiladigan xodimlarning haftalik jadvali (Umumiy ko'rinish).
  allWeekSchedules: (start?: string) =>
    apiFetch<WorkWeek[]>(`/work-schedule/all/week${start ? `?start=${start}` : ""}`),
  setWeeklySchedule: (userId: number, days: WorkDayEntry[]) =>
    apiFetch<WorkWeekly>(`/work-schedule/${userId}/weekly`, { method: "PUT", body: JSON.stringify({ days }) }),
  listScheduleOverrides: (userId: number, dateFrom?: string, dateTo?: string) => {
    const p = new URLSearchParams();
    if (dateFrom) p.set("date_from", dateFrom);
    if (dateTo) p.set("date_to", dateTo);
    const q = p.toString();
    return apiFetch<WorkOverride[]>(`/work-schedule/${userId}/overrides${q ? `?${q}` : ""}`);
  },
  setScheduleOverride: (
    userId: number,
    data: { date: string; is_working: boolean; start_time?: string | null; end_time?: string | null; note?: string | null }
  ) => apiFetch<WorkOverride>(`/work-schedule/${userId}/override`, { method: "PUT", body: JSON.stringify(data) }),
  deleteScheduleOverride: (userId: number, day: string) =>
    apiFetch<{ deleted: boolean }>(`/work-schedule/${userId}/override/${day}`, { method: "DELETE" }),
  listAuditLogs: (params: { action?: string; date_from?: string; date_to?: string } = {}) => {
    const query = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v) as [string, string][]
    ).toString();
    return apiFetch<AuditLog[]>(`/audit-logs${query ? `?${query}` : ""}`);
  },
  // --- Payroll (oylik ish haqi + kechikish jarimasi + qo'shimcha ish) ---
  listFinePolicies: () => apiFetch<FinePolicy[]>("/payroll/policies"),
  upsertFinePolicy: (data: FinePolicyInput) =>
    apiFetch<FinePolicy>("/payroll/policies", { method: "PUT", body: JSON.stringify(data) }),
  deleteFinePolicy: (policyId: number) =>
    apiFetch<{ deleted: boolean }>(`/payroll/policies/${policyId}`, { method: "DELETE" }),
  listSalaryRates: (userId: number) => apiFetch<SalaryRate[]>(`/payroll/rates?user_id=${userId}`),
  //  `reason` MAJBURIY (TZ 3.25 / S-25) — backend sababsiz stavkani rad
  //  etadi. Ro'yxat `/payroll/rates/reasons` dan olinadi.
  salaryReasons: () =>
    apiFetch<{ value: string; label: string }[]>("/payroll/rates/reasons"),
  mySalaryHistory: () => apiFetch<SalaryRate[]>("/payroll/rates/me"),
  createSalaryRate: (data: { user_id: number; amount: number; pay_basis: string; effective_from: string; reason: string; note?: string | null }) =>
    apiFetch<SalaryRate>("/payroll/rates", { method: "POST", body: JSON.stringify(data) }),
  // PATCH — faqat YUBORILGAN maydon o'zgaradi. `note: null` yuborish izohni
  // tozalaydi, shuning uchun uni "yubormaslik"dan farqlash kerak.
  updateSalaryRate: (
    rateId: number,
    data: { amount?: number; pay_basis?: string; effective_from?: string; note?: string | null }
  ) => apiFetch<SalaryRate>(`/payroll/rates/${rateId}`, { method: "PATCH", body: JSON.stringify(data) }),
  listKpiRates: () => apiFetch<KpiRate[]>("/payroll/kpi-rates"),
  createKpiRate: (data: {
    scope: string;
    scope_id: number | null;
    metric: string;
    amount: number;
    effective_from: string;
    note?: string | null;
  }) => apiFetch<KpiRate>("/payroll/kpi-rates", { method: "POST", body: JSON.stringify(data) }),
  listOvertimeProfiles: () => apiFetch<OvertimeProfile[]>("/payroll/overtime-profiles"),
  upsertOvertimeProfile: (userId: number, data: OvertimeProfileInput) =>
    apiFetch<OvertimeProfile>(`/payroll/overtime-profiles/${userId}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  // Bir necha (yoki hamma) xodimga bir vaqtda profil yozish.
  // `userIds` bo'sh -> barcha faol kuzatiladigan xodim.
  bulkApplyOvertimeProfile: (userIds: number[], data: OvertimeProfileInput) =>
    apiFetch<{ applied: number; created: number; updated: number }>(
      "/payroll/overtime-profiles/bulk",
      { method: "POST", body: JSON.stringify({ user_ids: userIds, profile: data }) }
    ),
  // Barcha xodimga default profil (§3.2) — xodim qatori bo'lsa u bosadi.
  upsertGlobalOvertimeProfile: (data: OvertimeProfileInput) =>
    apiFetch<OvertimeProfile>("/payroll/overtime-profiles/global", {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  listOvertimeEntries: (params: { period?: string; status_filter?: string } = {}) => {
    const q = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== "") as [string, string][]
    ).toString();
    return apiFetch<OvertimeEntry[]>(`/payroll/overtime${q ? `?${q}` : ""}`);
  },
  createOvertimeEntry: (data: { user_id: number; date: string; minutes: number; note?: string | null }) =>
    apiFetch<OvertimeEntry>("/payroll/overtime", { method: "POST", body: JSON.stringify(data) }),
  decideOvertimeEntry: (entryId: number, decision: "approved" | "rejected") =>
    apiFetch<OvertimeEntry>(`/payroll/overtime/${entryId}/decide`, {
      method: "POST",
      body: JSON.stringify({ status: decision }),
    }),
  // Bir oydagi BARCHA kutilayotgan yozuvni bir bosishda hal qilish.
  bulkDecideOvertime: (period: string, decision: "approved" | "rejected") =>
    apiFetch<{ period: string; status: string; decided: number }>("/payroll/overtime/bulk-decide", {
      method: "POST",
      body: JSON.stringify({ period, status: decision }),
    }),
  // «Hozir hisoblab ber» — cronni (01:00) kutmasdan nomzod yaratish.
  detectOvertimeNow: (targetDate?: string) =>
    apiFetch<{ date: string; created: number }>("/payroll/overtime/detect-now", {
      method: "POST",
      body: JSON.stringify({ target_date: targetDate ?? null }),
    }),
  createPayrollAdjustment: (data: { user_id: number; period: string; kind: "plus" | "minus"; amount: number; reason: string }) =>
    apiFetch<PayrollAdjustment>("/payroll/adjustments", { method: "POST", body: JSON.stringify(data) }),
  listPayrollAdjustments: (params: { period?: string; user_id?: number; category?: string } = {}) => {
    const q = new URLSearchParams(
      Object.entries(params)
        .filter(([, v]) => v !== undefined && v !== "")
        .map(([k, v]) => [k, String(v)])
    ).toString();
    return apiFetch<PayrollAdjustment[]>(`/payroll/adjustments${q ? `?${q}` : ""}`);
  },
  /** Xodimning o'z avanslari (kabinet). Shaxs TOKENDAN olinadi. */
  myAdvances: () => apiFetch<MyAdvances>("/payroll/me/advances"),

  // ── HR paneli va nazorat (D-01…D-03) ──
  advanceSummary: (period?: string) =>
    apiFetch<AdvanceDaySummary>(
      `/payroll/advance-summary${period ? `?period=${period}` : ""}`
    ),
  announceAdvanceDay: (body: { advance_date: string; note?: string | null }) =>
    apiFetch<AdvanceAnnouncement>("/payroll/advance-announce", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  advanceAnnouncements: () =>
    apiFetch<AdvanceAnnouncement[]>("/payroll/advance-announcements"),
  bulkDecideAdvances: (body: { ids: number[]; approve: boolean; note?: string | null }) =>
    apiFetch<{ decided: number; skipped: number; approved: boolean }>(
      "/payroll/advances/bulk-decide",
      { method: "POST", body: JSON.stringify(body) }
    ),

  // ── Avans sozlamalari (B-01/B-02) ──
  advanceSettings: () => apiFetch<AdvanceSettings[]>("/payroll/advance-settings"),
  upsertAdvanceSettings: (body: AdvanceSettingsInput) =>
    apiFetch<AdvanceSettings>("/payroll/advance-settings", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  deleteAdvanceSettings: (id: number) =>
    apiFetch<{ deleted: boolean }>(`/payroll/advance-settings/${id}`, { method: "DELETE" }),
  advanceLimit: (userId: number, period?: string) =>
    apiFetch<AdvanceLimit>(
      `/payroll/advances/limit?user_id=${userId}${period ? `&period=${period}` : ""}`
    ),
  createAdvance: (data: {
    user_id: number;
    period: string;
    amount: number;
    reason: string;
    // Yaqin summa/sana bilan avans allaqachon bo'lsa server 409 qaytaradi
    // (Avans TZ A-01). HR ogohlantirishni ko'rib «baribir kiritaman» desa,
    // shu bayroq bilan qayta yuboriladi.
    confirm_duplicate?: boolean;
    // Chegaradan oshiq kiritish — faqat Boshliq/Dasturchi, sabab bilan
    // (auditga «advance_over_limit» amali sifatida tushadi).
    override_limit?: boolean;
    override_reason?: string;
  }) => apiFetch<PayrollAdjustment>("/payroll/advances", { method: "POST", body: JSON.stringify(data) }),
  decideAdvance: (adjustmentId: number, data: { approve: boolean; note?: string | null }) =>
    apiFetch<PayrollAdjustment>(`/payroll/advances/${adjustmentId}/decide`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  /** «To'lab berildi» — kassa pulni berganini belgilaydi (A-04). Faqat
   *  tasdiqlangan avansda ishlaydi (server 400 beradi). */
  issueAdvance: (adjustmentId: number, data: { issued_on?: string; note?: string } = {}) =>
    apiFetch<PayrollAdjustment>(`/payroll/advances/${adjustmentId}/issue`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  /** YUMSHOQ o'chirish (A-05): qator bazada qoladi, sabab auditga yoziladi. */
  deletePayrollAdjustment: (adjustmentId: number, reason?: string) =>
    apiFetch<{ deleted: boolean; soft: boolean }>(
      `/payroll/adjustments/${adjustmentId}${reason ? `?reason=${encodeURIComponent(reason)}` : ""}`,
      { method: "DELETE" }
    ),
  listPayrollPeriods: () => apiFetch<PayrollPeriodSummary[]>("/payroll/periods"),
  payrollPreflight: (period: string) => apiFetch<PayrollPreflight>(`/payroll/${period}/preflight`),
  // Hisoblash NAVBATGA qo'yiladi (§4.3) — javob darhol keladi, natija emas.
  // Progressni `payrollCalcStatus` bilan kuzatish kerak.
  calculatePayroll: (period: string, userIds?: number[]) =>
    apiFetch<{ period: string; queued: boolean; total: number }>(`/payroll/${period}/calculate`, {
      method: "POST",
      body: JSON.stringify({ user_ids: userIds ?? null }),
    }),
  payrollCalcStatus: (period: string) =>
    apiFetch<PayrollCalcStatus>(`/payroll/${period}/status`),
  hrApprovePayrollPeriod: (period: string) =>
    apiFetch<{ period: string; status: string; payslip_count: number }>(
      `/payroll/${period}/hr-approve`,
      { method: "POST" }
    ),
  listPayslips: (period: string) => apiFetch<PayslipRow[]>(`/payroll/${period}`),
  payslipDetail: (period: string, userId: number) =>
    apiFetch<PayslipDetail>(`/payroll/${period}/user/${userId}`),
  approvePayrollPeriod: (period: string) =>
    apiFetch<{ period: string; approved: number }>(`/payroll/${period}/approve`, { method: "POST" }),
  myLateStatus: () => apiFetch<PayrollLateStatus>("/payroll/me/late-status"),
  // Xodim kabineti — o'z ish jadvali. `start` hafta ichidagi ISTALGAN sana
  // bo'lishi mumkin, backend dushanbaga tekislaydi (_week_start).
  myWorkWeek: (start?: string) =>
    apiFetch<WorkWeek>(`/work-schedule/me/week${start ? `?start=${start}` : ""}`),
  myPayslip: () => apiFetch<MyPayslip>("/payroll/me/payslip"),
  myTodayResult: () => apiFetch<DailyResultToday>("/daily-results/me/today"),
  myTasks: () => apiFetch<Task[]>("/tasks/me"),
  myHourlyPlan: () => apiFetch<HourlyPlan>("/hourly-plan/me"),
  myStats: () => apiFetch<MyStats>("/stats/me"),
  myBonuses: () => apiFetch<Bonus[]>("/bonuses/me"),
  myExcusedDays: () => apiFetch<ExcusedDay[]>("/excused-days/me"),
  // ── Ish kundaligi ──
  // Xodim: o'z oyi + bugunga yozuv qo'shish/tahrirlash/o'chirish. Sanani mijoz
  // YUBORMAYDI — backend har doim bugungi (Toshkent) kunga yozadi, tahrir esa
  // faqat o'sha kuni mumkin (aks holda 403).
  myWorkLog: (month?: string) =>
    apiFetch<WorkLogMonth>(`/work-log/me${month ? `?month=${month}` : ""}`),
  addMyWorkLogEntry: (data: { text: string }) =>
    apiFetch<WorkLogEntry>("/work-log/me", { method: "POST", body: JSON.stringify(data) }),
  editMyWorkLogEntry: (entryId: number, data: { text: string }) =>
    apiFetch<WorkLogEntry>(`/work-log/me/${entryId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  deleteMyWorkLogEntry: (entryId: number) =>
    apiFetch<{ deleted: boolean }>(`/work-log/me/${entryId}`, { method: "DELETE" }),
  // ── E'tiroz / Shikoyat ──
  myAppeals: () => apiFetch<Appeal[]>("/appeals/me"),
  // Tanada `telegram_id` YO'Q — shaxs tokendan (AppealMeCreate).
  createMyAppeal: (data: {
    kind: "objection" | "complaint";
    topic: string;
    text: string;
    is_anonymous?: boolean;
    recipient_role?: "hr" | "boss";
    ref_date?: string | null;
    ref_period?: string | null;
  }) => apiFetch<Appeal>("/appeals/me", { method: "POST", body: JSON.stringify(data) }),
  listAppeals: (params?: { status_filter?: string; kind?: string }) => {
    const q = new URLSearchParams();
    if (params?.status_filter) q.set("status_filter", params.status_filter);
    if (params?.kind) q.set("kind", params.kind);
    const s = q.toString();
    return apiFetch<Appeal[]>(`/appeals${s ? `?${s}` : ""}`);
  },
  reviewAppeal: (itemId: number) =>
    apiFetch<Appeal>(`/appeals/${itemId}/review`, { method: "POST" }),
  decideAppeal: (itemId: number, data: { decision: string; note: string }) =>
    apiFetch<AppealDecideResult>(`/appeals/${itemId}/decide`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  // ── Arizalar ──
  myRequests: () => apiFetch<EmployeeRequest[]>("/requests/me"),
  // Ish kunlari kalkulyatori — forma to'ldirilayotganda chaqiriladi.
  calcRequestRange: (start: string, end: string) =>
    apiFetch<RequestCalc>(`/requests/me/calc?start=${start}&end=${end}`),
  createMyRequest: (data: {
    kind: string;
    start_date?: string | null;
    end_date?: string | null;
    amount?: number | null;
    reason: string;
  }) => apiFetch<EmployeeRequest>("/requests/me", { method: "POST", body: JSON.stringify(data) }),
  cancelMyRequest: (itemId: number) =>
    apiFetch<EmployeeRequest>(`/requests/${itemId}/cancel`, { method: "POST" }),
  listRequests: (params?: { status_filter?: string; kind?: string }) => {
    const q = new URLSearchParams();
    if (params?.status_filter) q.set("status_filter", params.status_filter);
    if (params?.kind) q.set("kind", params.kind);
    const s = q.toString();
    return apiFetch<EmployeeRequest[]>(`/requests${s ? `?${s}` : ""}`);
  },
  decideRequest: (itemId: number, data: { decision: string; note: string }) =>
    apiFetch<RequestDecideResult>(`/requests/${itemId}/decide`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  // Bevosita rahbar qadami — izoh faqat rad etishda majburiy.
  managerDecideRequest: (itemId: number, data: { approve: boolean; note?: string }) =>
    apiFetch<EmployeeRequest>(`/requests/${itemId}/manager-decide`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  // «Ishdagi ta'tilchi»: qolgan ta'til kunlari bekor qilinsinmi.
  interruptRequest: (itemId: number, cut: boolean) =>
    apiFetch<RequestInterruptResult>(`/requests/${itemId}/interrupt`, {
      method: "POST",
      body: JSON.stringify({ cut }),
    }),
  myLeaveBalance: (year?: number) =>
    apiFetch<LeaveBalance>(`/requests/me/balance${year ? `?year=${year}` : ""}`),
  leaveBalance: (userId: number, year?: number) =>
    apiFetch<LeaveBalance>(`/requests/balance/${userId}${year ? `?year=${year}` : ""}`),
  // Tasdiqlangan arizani bekor qilish — yozilgan qatorlar qaytariladi.
  revokeRequest: (itemId: number, reason: string) =>
    apiFetch<RequestRevokeResult>(`/requests/${itemId}/revoke`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  // Rahbar: bitta xodim oyi + butun jamoa qamrovi.
  workLogMonth: (userId: number, month?: string) =>
    apiFetch<WorkLogMonth>(`/work-log?user_id=${userId}${month ? `&month=${month}` : ""}`),
  workLogCoverage: (month?: string) =>
    apiFetch<WorkLogCoverage>(`/work-log/coverage${month ? `?month=${month}` : ""}`),
  // Tanada `telegram_id` YO'Q — shaxs tokendan olinadi (ExcusedDayMeCreate).
  requestMyExcusedDay: (data: { reason: string; date?: string }) =>
    apiFetch<ExcusedDay>("/excused-days/me", { method: "POST", body: JSON.stringify(data) }),
  // Tanasi YO'Q: shaxs tokendan olinadi, ya'ni mijoz boshqa birovning
  // vazifasini yopa olmaydi (backend `assigned_to`ni tekshiradi).
  completeMyTask: (taskId: number) =>
    apiFetch<Task>(`/tasks/me/${taskId}/complete`, { method: "POST" }),
  downloadPayrollExport: async (period: string): Promise<void> => {
    const token = getToken();
    const resp = await fetch(`${API_BASE_URL}/payroll/${period}/export`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!resp.ok) {
      if (resp.status === 401) {
        window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
      }
      throw new ApiError(resp.status, "Ish haqi varag'ini yuklashda xatolik");
    }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `oylik_${period}.xlsx`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  },
  downloadReportExport: async (dateFrom: string, dateTo: string): Promise<void> => {
    const token = getToken();
    const resp = await fetch(`${API_BASE_URL}/reports/export?date_from=${dateFrom}&date_to=${dateTo}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!resp.ok) {
      if (resp.status === 401) {
        window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
      }
      throw new ApiError(resp.status, "Hisobotni yuklashda xatolik");
    }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `hisobot_${dateFrom}_${dateTo}.xlsx`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  },

  // --- Dasturchi rejimi (super-admin, OYLIK_JARIMA_REJASI.md 11-bo'lim) ---
  listAdminRecords: (entity: string) => apiFetch<AdminRecord[]>(`/admin/records/${entity}`),
  patchAdminRecord: (entity: string, id: number, fields: Record<string, unknown>, reason: string) =>
    apiFetch<AdminRecord>(`/admin/records/${entity}/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ fields, override_reason: reason }),
    }),
  deleteAdminRecord: (entity: string, id: number, reason: string, hard = false) =>
    apiFetch<{ deleted: boolean; hard: boolean }>(`/admin/records/${entity}/${id}?hard=${hard}`, {
      method: "DELETE",
      body: JSON.stringify({ override_reason: reason }),
    }),
  restoreAdminRecord: (entity: string, id: number, reason: string) =>
    apiFetch<{ restored: boolean }>(`/admin/records/${entity}/${id}/restore`, {
      method: "POST",
      body: JSON.stringify({ override_reason: reason }),
    }),
  adminSetNorm: (userId: number, metric: string, value: number, reason: string) =>
    apiFetch<AdminRecord>(`/admin/norms/${userId}/${metric}`, {
      method: "PUT",
      body: JSON.stringify({ value, override_reason: reason }),
    }),
  adminDeleteNorm: (normId: number, reason: string, hard = false) =>
    apiFetch<{ deleted: boolean; hard: boolean }>(`/admin/norms/${normId}?hard=${hard}`, {
      method: "DELETE",
      body: JSON.stringify({ override_reason: reason }),
    }),
  adminClearMetric: (userId: number, metric: string, reason: string) =>
    apiFetch<{ cleared: number }>(`/admin/norms/${userId}/${metric}`, {
      method: "DELETE",
      body: JSON.stringify({ override_reason: reason }),
    }),
  adminRevertNorm: (userId: number, metric: string, reason: string) =>
    apiFetch<{ reverted: boolean; current_value: number | null }>(
      `/admin/norms/${userId}/revert?metric=${encodeURIComponent(metric)}`,
      { method: "POST", body: JSON.stringify({ override_reason: reason }) }
    ),
  unlockPayrollPeriodAdmin: (period: string, reason: string) =>
    apiFetch<{ period: string; locked: boolean }>(`/admin/payroll/${period}/unlock`, {
      method: "POST",
      body: JSON.stringify({ override_reason: reason }),
    }),
  forceRecalculatePayrollAdmin: (period: string, reason: string) =>
    apiFetch<{ period: string; calculated: number }>(`/admin/payroll/${period}/force-recalculate`, {
      method: "POST",
      body: JSON.stringify({ override_reason: reason }),
    }),
  patchPayslipAdmin: (period: string, userId: number, fields: Record<string, unknown>, reason: string) =>
    apiFetch<AdminRecord>(`/admin/payroll/${period}/user/${userId}`, {
      method: "PATCH",
      body: JSON.stringify({ fields, override_reason: reason }),
    }),
  deletePayrollPeriodAdmin: (period: string, reason: string) =>
    apiFetch<{ deleted_payslips: number }>(`/admin/payroll/${period}`, {
      method: "DELETE",
      body: JSON.stringify({ override_reason: reason }),
    }),
  recalculateAttendanceAdmin: (dateFrom: string, dateTo: string, reason: string) =>
    apiFetch<{ recalculated: number }>(
      `/admin/attendance/recalculate?date_from=${dateFrom}&date_to=${dateTo}`,
      { method: "POST", body: JSON.stringify({ override_reason: reason }) }
    ),
  forceRoleAdmin: (userId: number, role: string, reason: string) =>
    apiFetch<{ user_id: number; role: string }>(`/admin/users/${userId}/force-role`, {
      method: "POST",
      body: JSON.stringify({ role, override_reason: reason }),
    }),
  listOverrideAudit: () => apiFetch<OverrideAuditRow[]>("/admin/audit/overrides"),
  // Davomat vaqtini tuzatish huquqi SHAXSAN berilganlar (rol bo'yicha
  // huquqi borlar — hr/boss/dasturchi — bu ro'yxatga kirmaydi).
  listAttendanceEditors: () => apiFetch<AttendanceEditorRow[]>("/admin/attendance-editors"),
  setAttendanceEditor: (userId: number, granted: boolean, reason: string) =>
    apiFetch<{ user_id: number; can_edit_attendance: boolean }>(
      `/admin/users/${userId}/attendance-editor`,
      { method: "POST", body: JSON.stringify({ granted, override_reason: reason }) }
    ),
  // ── Push (brauzer/PWA) ──
  // Shaxs FAQAT tokendan olinadi — mijoz `user_id` yubormaydi (backend
  // `/me/push/...` ostida, `get_current_user` bilan).
  registerPushToken: (token: string, platform: "web" | "android" | "ios") =>
    apiFetch<{ ok: boolean }>("/me/push/token", {
      method: "POST",
      body: JSON.stringify({ token, platform }),
    }),
  unregisterPushToken: (token: string, platform: "web" | "android" | "ios") =>
    apiFetch<{ ok: boolean }>("/me/push/token", {
      method: "DELETE",
      body: JSON.stringify({ token, platform }),
    }),
  pushSettings: () => apiFetch<PushSettingsOut>("/me/push/settings"),
  updatePushSettings: (categories: Record<string, boolean>) =>
    apiFetch<PushSettingsOut>("/me/push/settings", {
      method: "PUT",
      body: JSON.stringify({ categories }),
    }),
  // Tushuntirish xatlari (sababsiz kelmagan kun) — HR ko'radi va qaror qiladi.
  listExplanations: (statusFilter?: string) =>
    apiFetch<ExplanationRequestRow[]>(
      `/attendance/explanations${statusFilter ? `?status_filter=${statusFilter}` : ""}`
    ),
  decideExplanation: (reqId: number, accept: boolean, note?: string) =>
    apiFetch<ExplanationRequestRow>(`/attendance/explanations/${reqId}/decide`, {
      method: "POST",
      body: JSON.stringify({ accept, note: note || null }),
    }),
  // Kechikish/jarima qoidasini o'zgartirish huquqi (beruvchi: Boshliq yoki
  // Dasturchi — shuning uchun /admin EMAS, /payroll ostida).
  listFinePolicyEditors: () => apiFetch<AttendanceEditorRow[]>("/payroll/fine-policy-editors"),
  setFinePolicyEditor: (userId: number, granted: boolean, reason: string) =>
    apiFetch<{ user_id: number; can_edit_fine_policy: boolean }>(
      `/payroll/fine-policy-editors/${userId}`,
      { method: "POST", body: JSON.stringify({ granted, reason }) }
    ),
  // Sotuv voronkasi (VORONKA_TARIFLAR.md). Hisob lokal jadvallardan —
  // CRM'ga so'rov ketmaydi.
  funnel: (mode: "period" | "cohort", month?: string) =>
    apiFetch<FunnelData>(`/funnel?mode=${mode}${month ? `&month=${month}` : ""}`),
  funnelMonths: (months = 6) => apiFetch<FunnelMonths>(`/funnel/months?months=${months}`),
  funnelSettings: () => apiFetch<FunnelRules>("/funnel/settings"),
  saveFunnelSettings: (body: {
    cancelled_pipe_status_ids?: number[];
    subtract_cancelled?: boolean;
    low_quality_pipe_status_ids?: number[];
    exclude_low_quality?: boolean;
  }) => apiFetch<{ ok: boolean }>("/funnel/settings", {
    method: "POST",
    body: JSON.stringify(body),
  }),
  funnelAnalysis: (period: string) =>
    apiFetch<FunnelAnalysis>(`/funnel/analysis?period=${period}`),
  funnelOperators: (month: string) =>
    apiFetch<OperatorQuality>(`/funnel/operators?month=${month}`),
  funnelTargetProgress: (period: string) =>
    apiFetch<TargetProgress>(`/funnel/target/progress?period=${period}`),
  funnelTargetSplit: (period: string) =>
    apiFetch<TargetSplit>(`/funnel/target/split?period=${period}`),
  applyTargetSplit: (body: { period: string; metric: string; user_ids?: number[] | null }) =>
    apiFetch<{ ok: boolean; applied: number; skipped_no_permission: number; daily: number }>(
      "/funnel/target/split/apply",
      { method: "POST", body: JSON.stringify(body) }
    ),
  funnelTarget: (period: string, targetContracts?: number) =>
    apiFetch<TargetPlan>(
      `/funnel/target?period=${period}${
        targetContracts ? `&target_contracts=${targetContracts}` : ""
      }`
    ),
  saveFunnelTarget: (body: {
    period: string;
    target_contracts: number | null;
    assumptions: Record<string, number> | null;
  }) => apiFetch<{ ok: boolean }>("/funnel/target", {
    method: "POST",
    body: JSON.stringify(body),
  }),
  funnelEconomics: (period: string, groupBy: "tag" | "source" = "tag") =>
    apiFetch<Economics>(`/funnel/economics?period=${period}&group_by=${groupBy}`),
  funnelKnownChannels: (period: string, groupBy: "tag" | "source" = "tag") =>
    apiFetch<{ channels: { channel: string; leads: number }[] }>(
      `/funnel/economics/channels?period=${period}&group_by=${groupBy}`
    ),
  setAdSpend: (body: {
    period: string;
    channel: string;
    amount: number;
    reach?: number | null;
    note?: string | null;
  }) => apiFetch<{ ok: boolean; id: number }>("/funnel/economics/spend", {
    method: "POST",
    body: JSON.stringify(body),
  }),
  deleteAdSpend: (id: number) =>
    apiFetch<{ ok: boolean }>(`/funnel/economics/spend/${id}`, { method: "DELETE" }),
  setAvgDealProfit: (period: string, avg_deal_profit: number | null) =>
    apiFetch<{ ok: boolean }>("/funnel/economics/avg-profit", {
      method: "POST",
      body: JSON.stringify({ period, avg_deal_profit }),
    }),
  funnelChannels: (groupBy: "tag" | "source", month?: string) =>
    apiFetch<FunnelChannels>(
      `/funnel/channels?group_by=${groupBy}${month ? `&month=${month}` : ""}`
    ),
  // Tabrik videolari (tashrif/shartnoma -> umumiy guruh). Fayl serverda
  // saqlanmaydi: backend uni Telegram'ga uzatib `file_id` oladi.
  celebrationSettings: () =>
    apiFetch<{ items: CelebrationMediaRow[] }>("/celebration/settings"),
  uploadCelebrationMedia: (kind: string, file: File, caption: string) => {
    const form = new FormData();
    form.append("kind", kind);
    form.append("caption", caption);
    form.append("file", file);
    return apiUpload<{ ok: boolean; kind: string; file_type: string }>(
      "/celebration/settings/upload",
      form
    );
  },
  disableCelebrationMedia: (kind: string) =>
    apiFetch<{ ok: boolean; disabled: number }>(
      `/celebration/settings/disable?kind=${kind}`,
      { method: "POST" }
    ),
  testCelebrationMedia: (kind: string) =>
    apiFetch<{ ok: boolean }>(`/celebration/settings/test?kind=${kind}`, { method: "POST" }),
  // Joylashuvsiz («bez lokatsiya») check-in ruxsati.
  listLocationExempt: () => apiFetch<LocationExemptRow[]>("/admin/location-exempt"),
  setLocationExempt: (userId: number, granted: boolean, reason: string) =>
    apiFetch<{ user_id: number; skip_location_check: boolean }>(
      `/admin/users/${userId}/location-exempt`,
      { method: "POST", body: JSON.stringify({ granted, override_reason: reason }) }
    ),
  // ── Xodim murojaatlari (TZ 3.29 / S-28) ──
  myInquiries: () => apiFetch<HrInquiryItem[]>("/hr-inquiries/me"),
  askHr: (question: string) =>
    apiFetch<{
      id: number;
      category: string;
      category_label: string;
      notified: number;
      //  S-29: bilim bazasida tayyor javob topilsa shu to'ladi va
      //  HR ga xabar YUBORILMAYDI — xodim avval tasdiqlashi kerak.
      suggestion?: HrSuggestion;
    }>("/hr-inquiries/me", { method: "POST", body: JSON.stringify({ question }) }),
  resolveSuggestion: (inquiryId: number, entryId: number, accepted: boolean) =>
    apiFetch<{ ok: boolean; resolved: boolean; notified?: number }>(
      "/hr-inquiries/me/suggestion",
      {
        method: "POST",
        body: JSON.stringify({
          inquiry_id: inquiryId,
          entry_id: entryId,
          accepted,
        }),
      }
    ),
  hrFrequent: (limit = 10) =>
    apiFetch<HrFrequentReport>(`/hr-inquiries/frequent?limit=${limit}`),
  inquiryToKnowledge: (id: number) =>
    apiFetch<{ ok: boolean; entry_id: number; audience: string }>(
      `/hr-inquiries/${id}/to-knowledge`,
      { method: "POST" }
    ),
  inquiryCategories: () =>
    apiFetch<{ value: string; label: string }[]>("/hr-inquiries/categories"),
  hrInquiries: (params?: { status?: string; category?: string }) => {
    const q = new URLSearchParams();
    if (params?.status) q.set("status_filter", params.status);
    if (params?.category) q.set("category", params.category);
    const qs = q.toString();
    return apiFetch<HrInquiryItem[]>(`/hr-inquiries${qs ? `?${qs}` : ""}`);
  },
  hrInquiryStats: () => apiFetch<{ open: number }>("/hr-inquiries/stats"),
  answerInquiry: (id: number, answer: string) =>
    apiFetch<{ ok: boolean; delivered: boolean }>(`/hr-inquiries/${id}/answer`, {
      method: "POST",
      body: JSON.stringify({ answer }),
    }),
  setInquiryCategory: (id: number, category: string) =>
    apiFetch<{ ok: boolean; category: string }>(`/hr-inquiries/${id}/category`, {
      method: "PUT",
      body: JSON.stringify({ category }),
    }),
  closeInquiry: (id: number) =>
    apiFetch<{ ok: boolean }>(`/hr-inquiries/${id}/close`, { method: "POST" }),
  // ── O'quv paneli (TZ 3.1 / S-34) ──
  courses: () => apiFetch<CourseItem[]>("/courses"),
  courseReport: () => apiFetch<CourseReport>("/courses/report"),
  courseDetail: (id: number) => apiFetch<CourseDetail>(`/courses/${id}`),
  courseMaterialKinds: () =>
    apiFetch<{ value: string; label: string }[]>("/courses/material-kinds"),
  courseAudiences: () =>
    apiFetch<{ value: string; label: string }[]>("/courses/audiences"),
  createCourse: (body: {
    title: string;
    description?: string | null;
    pass_percent: number;
    max_attempts: number;
    is_mandatory: boolean;
  }) => apiFetch<CourseItem>("/courses", { method: "POST", body: JSON.stringify(body) }),
  updateCourse: (id: number, body: Record<string, unknown>) =>
    apiFetch<CourseItem>(`/courses/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  publishCourse: (id: number, value: boolean) =>
    apiFetch<{ ok: boolean; is_published: boolean }>(
      `/courses/${id}/publish?value=${value}`,
      { method: "POST" }
    ),
  deleteCourse: (id: number) =>
    apiFetch<{ ok: boolean }>(`/courses/${id}`, { method: "DELETE" }),
  addCourseMaterial: (
    id: number,
    body: {
      kind: string;
      title: string;
      body?: string | null;
      file_id?: string | null;
      url?: string | null;
    }
  ) =>
    apiFetch<{ id: number; position: number }>(`/courses/${id}/materials`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deleteCourseMaterial: (id: number, materialId: number) =>
    apiFetch<{ ok: boolean }>(`/courses/${id}/materials/${materialId}`, {
      method: "DELETE",
    }),
  addCourseQuestion: (
    id: number,
    body: {
      text: string;
      options: string[];
      correct_index: number | null;
      points: number;
    }
  ) =>
    apiFetch<{ id: number; position: number; is_open: boolean }>(
      `/courses/${id}/questions`,
      { method: "POST", body: JSON.stringify(body) }
    ),
  deleteCourseQuestion: (id: number, questionId: number) =>
    apiFetch<{ ok: boolean }>(`/courses/${id}/questions/${questionId}`, {
      method: "DELETE",
    }),
  importCourseQuestions: (id: number, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return apiUpload<{ added: number; title: string | null; fallback: boolean }>(
      `/courses/${id}/questions/import`,
      form
    );
  },
  assignCourse: (
    id: number,
    body: { audience: string; scope_ids?: unknown[] | null; due_date?: string | null }
  ) =>
    apiFetch<{ created: number; skipped: number; audience_size: number }>(
      `/courses/${id}/assign`,
      { method: "POST", body: JSON.stringify(body) }
    ),
  courseAssignments: (id: number) =>
    apiFetch<CourseAssignmentRow[]>(`/courses/${id}/assignments`),
  // ── O'quv paneli: xodim tomoni (TZ 3.1 / S-36) ──
  //  ⚠️ Bot bilan BITTA holatni o'qiydi — backend bir xil `_me_*`
  //  funksiyalaridan chiqadi (S-35).
  myCourses: () => apiFetch<MyCourseItem[]>("/courses/me/assignments"),
  myCourseProgress: (id: number) =>
    apiFetch<CourseProgress>(`/courses/me/${id}/progress`),
  myCourseNextMaterial: (id: number) =>
    apiFetch<CourseProgress>(`/courses/me/${id}/next-material`, { method: "POST" }),
  myCourseAnswer: (id: number, body: { text?: string | null; choice?: number | null }) =>
    apiFetch<CourseProgress>(`/courses/me/${id}/answer`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  myCourseFinish: (id: number) =>
    apiFetch<CourseResultOut>(`/courses/me/${id}/finish`, { method: "POST" }),
  myCourseRetry: (id: number) =>
    apiFetch<CourseProgress>(`/courses/me/${id}/retry`, { method: "POST" }),
  myCourseSendMaterial: (id: number) =>
    apiFetch<{ ok: boolean; delivered: boolean }>(
      `/courses/me/${id}/send-material`,
      { method: "POST" }
    ),
  // ── Tashkiliy tuzilma (TZ 3.16 / S-40) ──
  orgChart: () => apiFetch<OrgChart>("/org/chart"),
  orgMyPlace: () => apiFetch<OrgMyPlace>("/org/my-place"),
  orgAcknowledge: () =>
    apiFetch<{ ok: boolean; version: number }>("/org/my-place/acknowledge", {
      method: "POST",
    }),
  orgPosition: (id: number) => apiFetch<OrgPositionDetail>(`/org/positions/${id}`),
  orgSetParent: (id: number, parentId: number | null) =>
    apiFetch<{ ok: boolean }>(`/org/positions/${id}/parent`, {
      method: "PUT",
      body: JSON.stringify({ parent_position_id: parentId }),
    }),
  orgDescriptions: (id: number) =>
    apiFetch<JobDescriptionVersion[]>(`/org/positions/${id}/descriptions`),
  orgAddDescription: (
    id: number,
    body: {
      purpose?: string | null;
      duties: string[];
      rights: string[];
      responsibility: string[];
      requirements: string[];
      effective_from?: string | null;
    }
  ) =>
    apiFetch<{ id: number; version: number }>(`/org/positions/${id}/descriptions`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  orgProfile: () => apiFetch<CompanyProfileOut>("/org/profile"),
  orgSaveProfile: (body: {
    mission?: string | null;
    values?: string[];
    goals?: string[];
  }) => apiFetch<CompanyProfileOut>("/org/profile", {
    method: "PUT",
    body: JSON.stringify(body),
  }),
};
