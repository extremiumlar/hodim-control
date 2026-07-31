import { apiFetch, ApiError, API_BASE_URL, getToken, UNAUTHORIZED_EVENT } from "./client";
import type {
  AdminRecord,
  Attendance,
  AttendanceDashboard,
  AttendanceReadiness,
  AuditLog,
  Bonus,
  DailyResult,
  EmployeeAttendanceSummary,
  ExcusedDay,
  FinePolicy,
  FinePolicyInput,
  LateStatRow,
  ManualAttendancePayload,
  CrmOperatorRow,
  CrmVisitOperatorRow,
  LeadStageDay,
  LeadStageMonth,
  Office,
  OperatorSummary,
  OverrideAuditRow,
  OvertimeEntry,
  OvertimeProfile,
  OvertimeProfileInput,
  PayrollAdjustment,
  PayrollLateStatus,
  PayrollPeriodSummary,
  PayrollPreflight,
  PayslipDetail,
  PayslipRow,
  Position,
  RegisterFaceResult,
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
  attendanceEmployeeSummary: (days = 30) =>
    apiFetch<EmployeeAttendanceSummary[]>(`/attendance/employee-summary?days=${days}`),
  attendanceLateStats: (days = 30) =>
    apiFetch<LateStatRow[]>(`/attendance/late-stats?days=${days}`),
  deleteAttendance: (attendanceId: number) =>
    apiFetch<{ deleted: boolean }>(`/attendance/${attendanceId}`, { method: "DELETE" }),
  // HR/Boshliq qo'lda tuzatishi — Face ID/GPS ishlamay qolgan kunlar uchun.
  manualAttendance: (data: ManualAttendancePayload) =>
    apiFetch<Attendance>("/attendance/manual", { method: "PUT", body: JSON.stringify(data) }),
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
  }) =>
    apiFetch<{ user: User; invite_link: string }>("/users", {
      method: "POST",
      body: JSON.stringify(data),
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
  recordExcusedDayForUser: (data: { user_id: number; reason: string; date?: string }) =>
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
  appLoginStart: () =>
    apiFetch<{ login_token: string; deep_link: string; expires_at: string }>(
      "/auth/app-login/start",
      { method: "POST" }
    ),
  appLoginPoll: (loginToken: string) =>
    apiFetch<{ status: "pending" | "confirmed" | "expired"; token: { access_token: string; user: User } | null }>(
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
  createSalaryRate: (data: { user_id: number; amount: number; pay_basis: string; effective_from: string; note?: string | null }) =>
    apiFetch<SalaryRate>("/payroll/rates", { method: "POST", body: JSON.stringify(data) }),
  listOvertimeProfiles: () => apiFetch<OvertimeProfile[]>("/payroll/overtime-profiles"),
  upsertOvertimeProfile: (userId: number, data: OvertimeProfileInput) =>
    apiFetch<OvertimeProfile>(`/payroll/overtime-profiles/${userId}`, {
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
  createPayrollAdjustment: (data: { user_id: number; period: string; kind: "plus" | "minus"; amount: number; reason: string }) =>
    apiFetch<PayrollAdjustment>("/payroll/adjustments", { method: "POST", body: JSON.stringify(data) }),
  deletePayrollAdjustment: (adjustmentId: number) =>
    apiFetch<{ deleted: boolean }>(`/payroll/adjustments/${adjustmentId}`, { method: "DELETE" }),
  listPayrollPeriods: () => apiFetch<PayrollPeriodSummary[]>("/payroll/periods"),
  payrollPreflight: (period: string) => apiFetch<PayrollPreflight>(`/payroll/${period}/preflight`),
  calculatePayroll: (period: string, userIds?: number[]) =>
    apiFetch<{ period: string; calculated: number }>(`/payroll/${period}/calculate`, {
      method: "POST",
      body: JSON.stringify({ user_ids: userIds ?? null }),
    }),
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
};
