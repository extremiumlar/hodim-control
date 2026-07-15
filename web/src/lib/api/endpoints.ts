import { apiFetch, ApiError, API_BASE_URL, getToken, UNAUTHORIZED_EVENT } from "./client";
import type {
  Attendance,
  AttendanceDashboard,
  AuditLog,
  Bonus,
  DailyResult,
  EmployeeAttendanceSummary,
  ExcusedDay,
  CrmOperatorRow,
  CrmVisitOperatorRow,
  LeadStageDay,
  LeadStageMonth,
  Office,
  OperatorSummary,
  Position,
  StatsOverview,
  Task,
  TeamNormRow,
  User,
  WorkDayEntry,
  WorkOverride,
  WorkWeekly,
} from "./types";

export const api = {
  me: () => apiFetch<User>("/users/me"),
  // --- Davomat (kelib-ketish) ---
  myAttendanceToday: () => apiFetch<Attendance | null>("/attendance/me/today"),
  myCheckIn: (data: { latitude: number; longitude: number; face_descriptor: number[]; liveness: number }) =>
    apiFetch<Attendance>("/attendance/me/check-in", { method: "POST", body: JSON.stringify(data) }),
  myCheckOut: (data: { latitude: number; longitude: number; face_descriptor: number[]; liveness: number }) =>
    apiFetch<Attendance>("/attendance/me/check-out", { method: "POST", body: JSON.stringify(data) }),
  registerMyFace: (faceDescriptor: number[]) =>
    apiFetch<User>("/attendance/me/register-face", {
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
  deleteAttendance: (attendanceId: number) =>
    apiFetch<{ deleted: boolean }>(`/attendance/${attendanceId}`, { method: "DELETE" }),
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
  listDailyResults: (userId: number) => apiFetch<DailyResult[]>(`/daily-results?user_id=${userId}`),
  createManualDailyResult: (data: {
    user_id: number;
    date: string;
    conversations_count: number;
    visits_count: number;
  }) => apiFetch<DailyResult>("/daily-results/manual", { method: "POST", body: JSON.stringify(data) }),
  setManualMobilografVideos: (data: { user_id: number; date: string; confirmed_count: number }) =>
    apiFetch<{ user_id: number; date: string; confirmed_count: number }>("/mobilograf-videos/manual", {
      method: "POST",
      body: JSON.stringify(data),
    }),
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
};
