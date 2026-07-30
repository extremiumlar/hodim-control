/**
 * React Query hook'lari — har bir api metodi uchun useQuery/useMutation.
 * Mutation'lar muvaffaqiyatda tegishli query'larni invalidate qiladi,
 * xatoda toast.error ko'rsatadi (chaqiruvchi o'z onSuccess'ini qo'shishi mumkin).
 */
import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationOptions,
} from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "./api/endpoints";
import type { Office, Position, WorkDayEntry } from "./api/types";

// ─── Query kalitlari (invalidatsiya shu kalitlar orqali) ───
export const qk = {
  me: ["me"] as const,
  attendanceToday: ["attendance", "me", "today"] as const,
  attendance: (params?: object) => ["attendance", "list", params ?? {}] as const,
  attendanceDashboard: ["attendance", "dashboard"] as const,
  attendanceSummary: (days: number) => ["attendance", "summary", days] as const,
  attendanceLateStats: (days: number) => ["attendance", "late-stats", days] as const,
  attendanceReadiness: (params?: object) => ["attendance", "readiness", params ?? {}] as const,
  offices: ["offices"] as const,
  users: (role?: string, includeInactive?: boolean) =>
    ["users", role ?? "all", !!includeInactive] as const,
  user: (id: number) => ["users", "one", id] as const,
  inviteLink: (id: number) => ["users", "invite-link", id] as const,
  crmOperators: ["crm-operators"] as const,
  crmVisitOperators: ["crm-visit-operators"] as const,
  positions: (includeInactive?: boolean) => ["positions", !!includeInactive] as const,
  tasks: (dateFilter: string) => ["tasks", dateFilter] as const,
  excusedDays: (statusFilter?: string) => ["excused-days", statusFilter ?? "all"] as const,
  teamNorms: ["norms", "team"] as const,
  dailyResults: (userId: number) => ["daily-results", userId] as const,
  bonuses: (userId: number) => ["bonuses", userId] as const,
  leadStageMonth: (month?: string) => ["lead-stages", "month", month ?? "current"] as const,
  leadStageDay: (day: string, responsibleId?: number) =>
    ["lead-stages", "day", day, responsibleId ?? null] as const,
  myLeadStageMonth: (month?: string) => ["lead-stages", "me", "month", month ?? "current"] as const,
  myLeadStageDay: (day: string) => ["lead-stages", "me", "day", day] as const,
  statsOverview: (days: number, month?: string) => ["stats", "overview", days, month ?? null] as const,
  operatorSummary: (period: string, month?: string) =>
    ["stats", "operator-summary", period, month ?? null] as const,
  weeklySchedule: (userId: number) => ["work-schedule", userId, "weekly"] as const,
  scheduleOverrides: (userId: number, from?: string, to?: string) =>
    ["work-schedule", userId, "overrides", from ?? null, to ?? null] as const,
  auditLogs: (params?: object) => ["audit-logs", params ?? {}] as const,
  finePolicies: ["payroll", "policies"] as const,
  salaryRates: (userId: number) => ["payroll", "rates", userId] as const,
  overtimeProfiles: ["payroll", "overtime-profiles"] as const,
  overtimeEntries: (params?: object) => ["payroll", "overtime", params ?? {}] as const,
  payrollPeriods: ["payroll", "periods"] as const,
  payrollPreflight: (period: string) => ["payroll", "preflight", period] as const,
  payslips: (period: string) => ["payroll", "payslips", period] as const,
  payslipDetail: (period: string, userId: number) => ["payroll", "payslip", period, userId] as const,
  myLateStatus: ["payroll", "me", "late-status"] as const,
  // Xodim kabineti — hafta boshiga bog'langan kalit, aks holda "keyingi hafta"
  // bosilganda react-query eski haftani keshdan qaytarardi.
  myWorkWeek: (start?: string) => ["work-schedule", "me", "week", start ?? "current"] as const,
  myPayslip: ["payroll", "me", "payslip"] as const,
  myTodayResult: ["daily-results", "me", "today"] as const,
  myTasks: ["tasks", "me"] as const,
  myHourlyPlan: ["hourly-plan", "me"] as const,
  adminRecords: (entity: string) => ["admin", "records", entity] as const,
  adminAudit: ["admin", "audit"] as const,
};

// Mutation uchun umumiy wrapper: xatoda toast, muvaffaqiyatda kalitlarni invalidate.
function useApiMutation<TData, TVariables>(
  mutationFn: (vars: TVariables) => Promise<TData>,
  invalidate: readonly (readonly unknown[])[] = [],
  options?: Omit<UseMutationOptions<TData, Error, TVariables>, "mutationFn">
) {
  const qc = useQueryClient();
  return useMutation<TData, Error, TVariables>({
    mutationFn,
    ...options,
    onSuccess: (...args) => {
      for (const key of invalidate) {
        qc.invalidateQueries({ queryKey: key as unknown[] });
      }
      options?.onSuccess?.(...args);
    },
    onError: (...args) => {
      toast.error(args[0].message || "Xatolik yuz berdi");
      options?.onError?.(...args);
    },
  });
}

// ─── Davomat ───
export const useMyAttendanceToday = () =>
  useQuery({ queryKey: qk.attendanceToday, queryFn: api.myAttendanceToday });

export const useAttendanceList = (
  params: { user_id?: number; date_from?: string; date_to?: string; status_filter?: string } = {}
) => useQuery({ queryKey: qk.attendance(params), queryFn: () => api.listAttendance(params) });

// 4.8-band: "Hozir ofisda" jonli ma'lumot bo'lsa-da avval avtomatik
// yangilanmasdi — rahbar sahifani qo'lda "Yangilash" bosmasa, ro'yxat eskirib
// qolardi. 30 soniyada bir avtomatik yangilanadi (sahifa faol bo'lgandagina —
// react-query'ning o'z default xatti-harakati, fon rejimida so'rov ketmaydi).
export const useAttendanceDashboard = () =>
  useQuery({
    queryKey: qk.attendanceDashboard,
    queryFn: api.attendanceDashboard,
    refetchInterval: 30_000,
  });

export const useAttendanceEmployeeSummary = (days = 30) =>
  useQuery({ queryKey: qk.attendanceSummary(days), queryFn: () => api.attendanceEmployeeSummary(days) });

export const useAttendanceLateStats = (days = 30) =>
  useQuery({ queryKey: qk.attendanceLateStats(days), queryFn: () => api.attendanceLateStats(days) });

export const useAttendanceReadiness = (
  params: { date_from?: string; date_to?: string } = {},
  enabled = true
) =>
  useQuery({
    queryKey: qk.attendanceReadiness(params),
    queryFn: () => api.attendanceReadiness(params),
    enabled,
  });

// Faqat Dasturchi (backend ham tekshiradi) — sinov uchun davomat yozuvini o'chirish
export const useDeleteAttendance = () =>
  useApiMutation((attendanceId: number) => api.deleteAttendance(attendanceId), [["attendance"]]);

// HR/Boshliq qo'lda tuzatishi — barcha davomat ko'rinishlarini yangilaydi.
export const useManualAttendance = () =>
  useApiMutation(api.manualAttendance, [["attendance"]]);

export const useMyCheckIn = () =>
  useApiMutation(api.myCheckIn, [qk.attendanceToday, ["attendance"]]);

export const useMyCheckOut = () =>
  useApiMutation(api.myCheckOut, [qk.attendanceToday, ["attendance"]]);

export const useRegisterMyFace = () =>
  useApiMutation((descriptor: number[]) => api.registerMyFace(descriptor), [qk.me]);

// ─── Ofislar ───
export const useOffices = () => useQuery({ queryKey: qk.offices, queryFn: api.listOffices });

export const useCreateOffice = () =>
  useApiMutation(api.createOffice, [qk.offices]);

export const useUpdateOffice = () =>
  useApiMutation(
    ({ officeId, data }: { officeId: number; data: Partial<Omit<Office, "id" | "created_at">> }) =>
      api.updateOffice(officeId, data),
    [qk.offices]
  );

export const useDeleteOffice = () =>
  useApiMutation((officeId: number) => api.deleteOffice(officeId), [qk.offices]);

// ─── Foydalanuvchilar ───
export const useUsers = (role?: string, includeInactive = false) =>
  useQuery({ queryKey: qk.users(role, includeInactive), queryFn: () => api.listUsers(role, includeInactive) });

export const useUser = (userId: number, enabled = true) =>
  useQuery({ queryKey: qk.user(userId), queryFn: () => api.getUser(userId), enabled });

export const useInviteLink = (userId: number, enabled = true) =>
  useQuery({ queryKey: qk.inviteLink(userId), queryFn: () => api.inviteLink(userId), enabled });

export const useCrmOperators = () =>
  useQuery({ queryKey: qk.crmOperators, queryFn: api.listCrmOperators });

export const useCrmVisitOperators = () =>
  useQuery({ queryKey: qk.crmVisitOperators, queryFn: api.listCrmVisitOperators });

export const useCreateUser = () => useApiMutation(api.createUser, [["users"]]);

export const useUpdateCrmExternalId = () =>
  useApiMutation(
    ({ userId, crmExternalId }: { userId: number; crmExternalId: string | null }) =>
      api.updateCrmExternalId(userId, crmExternalId),
    [["users"], qk.crmOperators]
  );

export const useUpdateCrmVisitExternalId = () =>
  useApiMutation(
    ({ userId, crmVisitExternalId }: { userId: number; crmVisitExternalId: string | null }) =>
      api.updateCrmVisitExternalId(userId, crmVisitExternalId),
    [["users"], qk.crmVisitOperators]
  );

export const useUpdateRole = () =>
  useApiMutation(
    ({ userId, role }: { userId: number; role: string }) => api.updateRole(userId, role),
    [["users"]]
  );

export const useUpdateUserPosition = () =>
  useApiMutation(
    ({ userId, positionId }: { userId: number; positionId: number | null }) =>
      api.updateUserPosition(userId, positionId),
    [["users"], qk.teamNorms]
  );

export const useUpdateUserSeat = () =>
  useApiMutation(
    ({ userId, isSeat }: { userId: number; isSeat: boolean }) => api.updateUserSeat(userId, isSeat),
    [["users"]]
  );

export const useDeleteUser = () => useApiMutation((userId: number) => api.deleteUser(userId), [["users"]]);

export const useDeactivateUser = () =>
  useApiMutation((userId: number) => api.deactivateUser(userId), [["users"]]);

export const useActivateUser = () =>
  useApiMutation((userId: number) => api.activateUser(userId), [["users"]]);

export const useResetAccount = () =>
  useApiMutation((userId: number) => api.resetAccount(userId), [["users"]]);

// ─── Lavozimlar ───
export const usePositions = (includeInactive = false) =>
  useQuery({ queryKey: qk.positions(includeInactive), queryFn: () => api.listPositions(includeInactive) });

export const useCreatePosition = () => useApiMutation(api.createPosition, [["positions"]]);

export const useUpdatePosition = () =>
  useApiMutation(
    ({ positionId, data }: { positionId: number; data: Parameters<typeof api.updatePosition>[1] }) =>
      api.updatePosition(positionId, data),
    [["positions"], ["users"]]
  );

// ─── Vazifalar ───
export const useTasks = (dateFilter = "today") =>
  useQuery({ queryKey: qk.tasks(dateFilter), queryFn: () => api.listTasks(dateFilter) });

export const useCreateTask = () => useApiMutation(api.createTask, [["tasks"]]);

export const useCreateBulkTasks = () => useApiMutation(api.createBulkTasks, [["tasks"]]);

export const useCancelTask = () => useApiMutation((taskId: number) => api.cancelTask(taskId), [["tasks"]]);

export const useDeleteTask = () => useApiMutation((taskId: number) => api.deleteTask(taskId), [["tasks"]]);

// ─── Sababli kunlar ───
export const useExcusedDays = (statusFilter?: string) =>
  useQuery({ queryKey: qk.excusedDays(statusFilter), queryFn: () => api.listExcusedDays(statusFilter) });

// ─── Normalar ───
export const useTeamNorms = () => useQuery({ queryKey: qk.teamNorms, queryFn: api.teamNorms });

export const useUpdateNorm = () => useApiMutation(api.updateNorm, [qk.teamNorms]);

// ─── Kunlik natijalar / bonuslar ───
export const useDailyResults = (userId: number, enabled = true) =>
  useQuery({ queryKey: qk.dailyResults(userId), queryFn: () => api.listDailyResults(userId), enabled });

export const useCreateManualDailyResult = () =>
  useApiMutation(api.createManualDailyResult, [["daily-results"], qk.teamNorms]);

export const useSetManualMobilografVideos = () =>
  useApiMutation(api.setManualMobilografVideos, [["daily-results"], qk.teamNorms]);

export const useBonuses = (userId: number, enabled = true) =>
  useQuery({ queryKey: qk.bonuses(userId), queryFn: () => api.listBonuses(userId), enabled });

// ─── Lidlar ───
export const useLeadStageMonth = (month?: string, isManager = true) =>
  useQuery({
    queryKey: isManager ? qk.leadStageMonth(month) : qk.myLeadStageMonth(month),
    queryFn: () => (isManager ? api.leadStageMonth(month) : api.myLeadStageMonth(month)),
  });

export const useLeadStageDay = (day: string | null, responsibleId?: number, isManager = true) =>
  useQuery({
    queryKey: day
      ? isManager
        ? qk.leadStageDay(day, responsibleId)
        : qk.myLeadStageDay(day)
      : ["lead-stages", "day", "none"],
    queryFn: () => (isManager ? api.leadStageDay(day!, responsibleId) : api.myLeadStageDay(day!)),
    enabled: !!day,
  });

// ─── Statistika ───
export const useStatsOverview = (days = 30, month?: string) =>
  useQuery({ queryKey: qk.statsOverview(days, month), queryFn: () => api.statsOverview(days, month) });

export const useOperatorSummary = (period: string, month?: string) =>
  useQuery({ queryKey: qk.operatorSummary(period, month), queryFn: () => api.operatorSummary(period, month) });

// ─── Ish jadvali ───
export const useWeeklySchedule = (userId: number, enabled = true) =>
  useQuery({ queryKey: qk.weeklySchedule(userId), queryFn: () => api.getWeeklySchedule(userId), enabled });

export const useSetWeeklySchedule = () =>
  useApiMutation(
    ({ userId, days }: { userId: number; days: WorkDayEntry[] }) => api.setWeeklySchedule(userId, days),
    [["work-schedule"]]
  );

export const useScheduleOverrides = (userId: number, dateFrom?: string, dateTo?: string, enabled = true) =>
  useQuery({
    queryKey: qk.scheduleOverrides(userId, dateFrom, dateTo),
    queryFn: () => api.listScheduleOverrides(userId, dateFrom, dateTo),
    enabled,
  });

export const useSetScheduleOverride = () =>
  useApiMutation(
    ({ userId, data }: { userId: number; data: Parameters<typeof api.setScheduleOverride>[1] }) =>
      api.setScheduleOverride(userId, data),
    [["work-schedule"]]
  );

export const useDeleteScheduleOverride = () =>
  useApiMutation(
    ({ userId, day }: { userId: number; day: string }) => api.deleteScheduleOverride(userId, day),
    [["work-schedule"]]
  );

// ─── Audit ───
export const useAuditLogs = (params: { action?: string; date_from?: string; date_to?: string } = {}) =>
  useQuery({ queryKey: qk.auditLogs(params), queryFn: () => api.listAuditLogs(params) });

// ─── Hisobot eksporti ───
export const useDownloadReport = () =>
  useApiMutation(
    ({ dateFrom, dateTo }: { dateFrom: string; dateTo: string }) =>
      api.downloadReportExport(dateFrom, dateTo),
    []
  );

// ─── Payroll (oylik ish haqi + kechikish jarimasi + qo'shimcha ish) ───
export const useFinePolicies = () =>
  useQuery({ queryKey: qk.finePolicies, queryFn: api.listFinePolicies });

export const useUpsertFinePolicy = () =>
  useApiMutation(api.upsertFinePolicy, [qk.finePolicies]);

export const useDeleteFinePolicy = () =>
  useApiMutation((policyId: number) => api.deleteFinePolicy(policyId), [qk.finePolicies]);

export const useSalaryRates = (userId: number, enabled = true) =>
  useQuery({ queryKey: qk.salaryRates(userId), queryFn: () => api.listSalaryRates(userId), enabled });

export const useCreateSalaryRate = () =>
  useApiMutation(api.createSalaryRate, [["payroll", "rates"]]);

export const useOvertimeProfiles = () =>
  useQuery({ queryKey: qk.overtimeProfiles, queryFn: api.listOvertimeProfiles });

export const useUpsertOvertimeProfile = () =>
  useApiMutation(
    ({ userId, data }: { userId: number; data: Parameters<typeof api.upsertOvertimeProfile>[1] }) =>
      api.upsertOvertimeProfile(userId, data),
    [qk.overtimeProfiles]
  );

export const useOvertimeEntries = (params: { period?: string; status_filter?: string } = {}) =>
  useQuery({ queryKey: qk.overtimeEntries(params), queryFn: () => api.listOvertimeEntries(params) });

export const useCreateOvertimeEntry = () =>
  useApiMutation(api.createOvertimeEntry, [["payroll", "overtime"]]);

export const useDecideOvertimeEntry = () =>
  useApiMutation(
    ({ entryId, decision }: { entryId: number; decision: "approved" | "rejected" }) =>
      api.decideOvertimeEntry(entryId, decision),
    [["payroll", "overtime"]]
  );

export const useCreatePayrollAdjustment = () =>
  useApiMutation(api.createPayrollAdjustment, [["payroll", "payslips"], ["payroll", "payslip"]]);

export const useDeletePayrollAdjustment = () =>
  useApiMutation(
    (adjustmentId: number) => api.deletePayrollAdjustment(adjustmentId),
    [["payroll", "payslips"], ["payroll", "payslip"]]
  );

export const usePayrollPeriods = () =>
  useQuery({ queryKey: qk.payrollPeriods, queryFn: api.listPayrollPeriods });

export const usePayrollPreflight = (period: string, enabled = true) =>
  useQuery({ queryKey: qk.payrollPreflight(period), queryFn: () => api.payrollPreflight(period), enabled });

export const useCalculatePayroll = () =>
  useApiMutation(
    ({ period, userIds }: { period: string; userIds?: number[] }) => api.calculatePayroll(period, userIds),
    [["payroll", "payslips"], ["payroll", "payslip"], qk.payrollPeriods, ["payroll", "preflight"]]
  );

export const usePayslips = (period: string, enabled = true) =>
  useQuery({ queryKey: qk.payslips(period), queryFn: () => api.listPayslips(period), enabled });

export const usePayslipDetail = (period: string, userId: number, enabled = true) =>
  useQuery({
    queryKey: qk.payslipDetail(period, userId),
    queryFn: () => api.payslipDetail(period, userId),
    enabled,
  });

export const useApprovePayrollPeriod = () =>
  useApiMutation(
    (period: string) => api.approvePayrollPeriod(period),
    [["payroll", "payslips"], ["payroll", "payslip"], qk.payrollPeriods]
  );

export const useMyLateStatus = () =>
  useQuery({ queryKey: qk.myLateStatus, queryFn: api.myLateStatus });

// ─── Xodim kabineti ───
export const useMyWorkWeek = (start?: string) =>
  useQuery({
    queryKey: qk.myWorkWeek(start),
    queryFn: () => api.myWorkWeek(start),
    // Hafta almashtirilganda yangi kalit bo'sh keladi va sahifa butunlay
    // skeletonga aylanardi — navigatsiya tugmalari YO'QOLIB, keyin qaytadi.
    // Sekin internetda bu bezovta qiladi. Oldingi haftani ko'rsatib turamiz.
    placeholderData: keepPreviousData,
  });

export const useMyPayslip = () =>
  useQuery({ queryKey: qk.myPayslip, queryFn: api.myPayslip });

export const useMyTodayResult = () =>
  useQuery({ queryKey: qk.myTodayResult, queryFn: api.myTodayResult });

export const useMyTasks = () => useQuery({ queryKey: qk.myTasks, queryFn: api.myTasks });

// Reja soat sayin o'zgaradi (this_hour_target, cumulative_target) — 30s
// staleTime yetarli, lekin sahifa ochiq turganda ham yangilanib tursin.
export const useMyHourlyPlan = () =>
  useQuery({ queryKey: qk.myHourlyPlan, queryFn: api.myHourlyPlan, refetchInterval: 120_000 });

// Muvaffaqiyatda ["tasks"] invalidatsiya qilinadi — ["tasks","me"] ham shunga
// kiradi, ya'ni ro'yxat o'zi yangilanadi. Rahbar vazifalar sahifasi ham
// yangilanadi (bir xil prefiks) — bu to'g'ri, holat haqiqatan o'zgardi.
export const useCompleteMyTask = () =>
  useApiMutation((taskId: number) => api.completeMyTask(taskId), [["tasks"]]);

export const useDownloadPayrollExport = () =>
  useApiMutation((period: string) => api.downloadPayrollExport(period), []);

// ─── Dasturchi rejimi (super-admin) ───
export const useAdminRecords = (entity: string, enabled = true) =>
  useQuery({ queryKey: qk.adminRecords(entity), queryFn: () => api.listAdminRecords(entity), enabled });

export const usePatchAdminRecord = (entity: string) =>
  useApiMutation(
    ({ id, fields, reason }: { id: number; fields: Record<string, unknown>; reason: string }) =>
      api.patchAdminRecord(entity, id, fields, reason),
    [qk.adminRecords(entity), qk.adminAudit]
  );

export const useDeleteAdminRecord = (entity: string) =>
  useApiMutation(
    ({ id, reason, hard }: { id: number; reason: string; hard?: boolean }) =>
      api.deleteAdminRecord(entity, id, reason, hard),
    [qk.adminRecords(entity), qk.adminAudit]
  );

export const useRestoreAdminRecord = (entity: string) =>
  useApiMutation(
    ({ id, reason }: { id: number; reason: string }) => api.restoreAdminRecord(entity, id, reason),
    [qk.adminRecords(entity), qk.adminAudit]
  );

export const useAdminSetNorm = () =>
  useApiMutation(
    ({ userId, metric, value, reason }: { userId: number; metric: string; value: number; reason: string }) =>
      api.adminSetNorm(userId, metric, value, reason),
    [qk.teamNorms, qk.adminAudit]
  );

export const useAdminDeleteNorm = () =>
  useApiMutation(
    ({ normId, reason, hard }: { normId: number; reason: string; hard?: boolean }) =>
      api.adminDeleteNorm(normId, reason, hard),
    [qk.teamNorms, qk.adminAudit, qk.adminRecords("norm")]
  );

export const useAdminClearMetric = () =>
  useApiMutation(
    ({ userId, metric, reason }: { userId: number; metric: string; reason: string }) =>
      api.adminClearMetric(userId, metric, reason),
    [qk.teamNorms, qk.adminAudit, qk.adminRecords("norm")]
  );

export const useAdminRevertNorm = () =>
  useApiMutation(
    ({ userId, metric, reason }: { userId: number; metric: string; reason: string }) =>
      api.adminRevertNorm(userId, metric, reason),
    [qk.teamNorms, qk.adminAudit, qk.adminRecords("norm")]
  );

export const useUnlockPayrollPeriodAdmin = () =>
  useApiMutation(
    ({ period, reason }: { period: string; reason: string }) => api.unlockPayrollPeriodAdmin(period, reason),
    [["payroll", "payslips"], qk.payrollPeriods, qk.adminAudit]
  );

export const useForceRecalculatePayrollAdmin = () =>
  useApiMutation(
    ({ period, reason }: { period: string; reason: string }) =>
      api.forceRecalculatePayrollAdmin(period, reason),
    [["payroll", "payslips"], ["payroll", "payslip"], qk.payrollPeriods, qk.adminAudit]
  );

export const usePatchPayslipAdmin = () =>
  useApiMutation(
    ({ period, userId, fields, reason }: {
      period: string; userId: number; fields: Record<string, unknown>; reason: string;
    }) => api.patchPayslipAdmin(period, userId, fields, reason),
    [["payroll", "payslips"], ["payroll", "payslip"], qk.adminAudit]
  );

export const useDeletePayrollPeriodAdmin = () =>
  useApiMutation(
    ({ period, reason }: { period: string; reason: string }) => api.deletePayrollPeriodAdmin(period, reason),
    [["payroll", "payslips"], ["payroll", "payslip"], qk.payrollPeriods, qk.adminAudit]
  );

export const useRecalculateAttendanceAdmin = () =>
  useApiMutation(
    ({ dateFrom, dateTo, reason }: { dateFrom: string; dateTo: string; reason: string }) =>
      api.recalculateAttendanceAdmin(dateFrom, dateTo, reason),
    [["attendance"], qk.adminAudit]
  );

export const useForceRoleAdmin = () =>
  useApiMutation(
    ({ userId, role, reason }: { userId: number; role: string; reason: string }) =>
      api.forceRoleAdmin(userId, role, reason),
    [["users"], qk.adminAudit]
  );

export const useOverrideAudit = () =>
  useQuery({ queryKey: qk.adminAudit, queryFn: api.listOverrideAudit });
