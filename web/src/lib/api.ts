const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export const UNAUTHORIZED_EVENT = "auth:unauthorized";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

function getToken(): string | null {
  return localStorage.getItem("access_token");
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const resp = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });

  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      detail = body.detail || detail;
    } catch {
      // ignore
    }
    if (resp.status === 401) {
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    }
    throw new ApiError(resp.status, detail);
  }

  if (resp.status === 204) {
    return undefined as T;
  }
  return (await resp.json()) as T;
}

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
  crm_external_id: string | null;
  created_at: string;
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
}

export interface TeamNormMetric {
  key: string;
  label: string;
  value: number | null;
}

export interface TeamNormRow {
  user_id: number;
  full_name: string;
  position_name: string | null;
  can_edit: boolean;
  metrics: TeamNormMetric[];
  suhbat: number | null;
  tashrif: number | null;
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

export const api = {
  me: () => apiFetch<User>("/users/me"),
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
  deactivateUser: (userId: number) => apiFetch<User>(`/users/${userId}/deactivate`, { method: "POST" }),
  activateUser: (userId: number) => apiFetch<User>(`/users/${userId}/activate`, { method: "POST" }),
  resetAccount: (userId: number) =>
    apiFetch<{ user: User; invite_link: string }>(`/users/${userId}/reset-account`, { method: "POST" }),
  listTasks: (dateFilter = "today") => apiFetch<Task[]>(`/tasks?date_filter=${dateFilter}`),
  createTask: (data: { assigned_to: number; title: string; description?: string; deadline?: string | null }) =>
    apiFetch<Task>("/tasks", { method: "POST", body: JSON.stringify(data) }),
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
  listBonuses: (userId: number) => apiFetch<Bonus[]>(`/bonuses?user_id=${userId}`),
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
