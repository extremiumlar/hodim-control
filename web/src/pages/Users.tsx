import { FormEvent, useEffect, useState } from "react";
import { api, CrmOperatorRow, Position, User } from "../lib/api";
import { useAuth } from "../lib/auth";

const ROLE_LABELS: Record<string, string> = {
  employee: "Xodim",
  hr: "HR",
  rop: "ROP",
  boss: "Boshliq",
  dasturchi: "Dasturchi",
};

export default function Users() {
  const { user: currentUser } = useAuth();
  const isBoss = currentUser?.role === "boss";
  const isDasturchi = currentUser?.role === "dasturchi";
  // Dasturchi — Boshliq bilan bir xil (aslida undan ham kengroq: majburiy o'chirish
  // huquqi bilan) to'liq boshqaruv huquqiga ega.
  const hasFullControl = isBoss || isDasturchi;
  const canCreateUser = currentUser?.role === "hr" || hasFullControl;
  // Lavozim biriktirish: HR/Boshliq/Dasturchi (backend PATCH /users/{id}/position bilan mos)
  const canSetPosition = canCreateUser;

  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState("employee");
  const [crmExternalIdForCreate, setCrmExternalIdForCreate] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [lastInviteLink, setLastInviteLink] = useState<string | null>(null);

  const [crmDrafts, setCrmDrafts] = useState<Record<number, string>>({});
  const [savingCrmId, setSavingCrmId] = useState<number | null>(null);
  const [savingRole, setSavingRole] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const [operators, setOperators] = useState<CrmOperatorRow[]>([]);
  const [operatorLinkChoice, setOperatorLinkChoice] = useState<Record<string, string>>({});
  const [linkingOperator, setLinkingOperator] = useState<string | null>(null);

  const [positions, setPositions] = useState<Position[]>([]);
  const [savingPosition, setSavingPosition] = useState<number | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const data = await api.listUsers(undefined, true);
      setUsers(data);
      const drafts: Record<number, string> = {};
      data.forEach((u) => {
        drafts[u.id] = u.crm_external_id ?? "";
      });
      setCrmDrafts(drafts);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Yuklashda xatolik");
    } finally {
      setLoading(false);
    }
  };

  const loadOperators = async () => {
    try {
      setOperators(await api.listCrmOperators());
    } catch {
      // CRM sozlanmagan bo'lishi mumkin — jim o'tkazamiz, bu bo'lim faqat boss uchun ixtiyoriy
    }
  };

  const loadPositions = async () => {
    try {
      setPositions(await api.listPositions());
    } catch {
      // Lavozimlar hali sozlanmagan bo'lishi mumkin — jim o'tkazamiz
    }
  };

  useEffect(() => {
    load();
    loadPositions();
    if (hasFullControl) loadOperators();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasFullControl]);

  const handlePositionChange = async (userId: number, value: string) => {
    setSavingPosition(userId);
    setError(null);
    try {
      await api.updateUserPosition(userId, value ? Number(value) : null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Lavozimni o'zgartirishda xatolik");
    } finally {
      setSavingPosition(null);
    }
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!fullName) return;
    setSubmitting(true);
    setError(null);
    setLastInviteLink(null);
    try {
      const { invite_link } = await api.createUser({
        full_name: fullName,
        role,
        crm_external_id: hasFullControl && crmExternalIdForCreate ? crmExternalIdForCreate.trim() : undefined,
      });
      setLastInviteLink(invite_link);
      setFullName("");
      setCrmExternalIdForCreate("");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Foydalanuvchi yaratishda xatolik");
    } finally {
      setSubmitting(false);
    }
  };

  const showInviteLink = async (userId: number) => {
    setError(null);
    setLastInviteLink(null);
    try {
      const { invite_link, already_started } = await api.inviteLink(userId);
      if (already_started) {
        setError("Bu foydalanuvchi botni allaqachon ishga tushirgan.");
      } else {
        setLastInviteLink(invite_link);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Havolani olishda xatolik");
    }
  };

  const saveCrmExternalId = async (userId: number) => {
    setSavingCrmId(userId);
    setError(null);
    try {
      const value = crmDrafts[userId]?.trim() || null;
      await api.updateCrmExternalId(userId, value);
      await load();
      await loadOperators();
    } catch (e) {
      setError(e instanceof Error ? e.message : "CRM ID saqlashda xatolik");
    } finally {
      setSavingCrmId(null);
    }
  };

  const handleRoleChange = async (userId: number, newRole: string) => {
    if (!window.confirm(`Rolni "${ROLE_LABELS[newRole] ?? newRole}"ga o'zgartirishni tasdiqlaysizmi?`)) return;
    setSavingRole(userId);
    setError(null);
    try {
      await api.updateRole(userId, newRole);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Rolni o'zgartirishda xatolik");
    } finally {
      setSavingRole(null);
    }
  };

  const handleDeactivate = async (userId: number) => {
    if (!window.confirm("Bu foydalanuvchini o'chirishni tasdiqlaysizmi? (keyinroq tiklash mumkin)")) return;
    setError(null);
    try {
      await api.deactivateUser(userId);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "O'chirishda xatolik");
    }
  };

  const handleActivate = async (userId: number) => {
    setError(null);
    try {
      await api.activateUser(userId);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Tiklashda xatolik");
    }
  };

  const handleResetAccount = async (userId: number) => {
    if (
      !window.confirm(
        "Akkaunt qayta bog'lansa, eski Telegram ulanishi bekor bo'ladi va yangi havola yaratiladi. Davom etaymi?"
      )
    )
      return;
    setError(null);
    setLastInviteLink(null);
    try {
      const { invite_link } = await api.resetAccount(userId);
      setLastInviteLink(invite_link);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Akkauntni qayta bog'lashda xatolik");
    }
  };

  const handleDelete = async (userId: number, fullNameLabel: string) => {
    const confirmText = isDasturchi
      ? `"${fullNameLabel}"ni bazadan BUTUNLAY o'chirmoqchimisiz? Bu amalni ORTGA QAYTARIB BO'LMAYDI. ` +
        `Dasturchi sifatida bu xodimga norma belgilangan yoki vazifa berilgan bo'lsa ham, ` +
        `unga bog'liq BARCHA ma'lumotlar (vazifa, norma, kunlik natija, mobilograf, sababli kun, bonus) ` +
        `birga o'chiriladi.`
      : `"${fullNameLabel}"ni bazadan BUTUNLAY o'chirmoqchimisiz? Bu amalni ORTGA QAYTARIB BO'LMAYDI. ` +
        `Agar bu foydalanuvchida tarixiy ma'lumot (vazifa, norma va h.k.) bo'lsa, o'chirish rad etiladi.`;
    if (!window.confirm(confirmText)) return;
    setDeletingId(userId);
    setError(null);
    try {
      await api.deleteUser(userId);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Butunlay o'chirishda xatolik");
    } finally {
      setDeletingId(null);
    }
  };

  const handleLinkOperator = async (externalId: string) => {
    const targetUserId = operatorLinkChoice[externalId];
    if (!targetUserId) return;
    setLinkingOperator(externalId);
    setError(null);
    try {
      await api.updateCrmExternalId(Number(targetUserId), externalId);
      await load();
      await loadOperators();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Bog'lashda xatolik");
    } finally {
      setLinkingOperator(null);
    }
  };

  const telegramConnectedUsers = users.filter((u) => u.bot_started);

  return (
    <div className="space-y-6">
      {error && <p className="text-sm text-red-600">{error}</p>}
      <div className={`grid gap-6 ${canCreateUser ? "md:grid-cols-3" : ""}`}>
        {canCreateUser && (
          <div className="md:col-span-1 bg-white rounded-lg shadow p-5 h-fit">
            <h2 className="font-semibold mb-4">Foydalanuvchi qo'shish</h2>
            <form onSubmit={handleSubmit} className="space-y-3">
              <div>
                <label className="block text-sm text-slate-600 mb-1">To'liq ism</label>
                <input
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  required
                  className="w-full border rounded px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="block text-sm text-slate-600 mb-1">Rol</label>
                <select
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                  className="w-full border rounded px-3 py-2 text-sm"
                >
                  {Object.entries(ROLE_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>
              {hasFullControl && (
                <div>
                  <label className="block text-sm text-slate-600 mb-1">CRM ID (ixtiyoriy)</label>
                  <input
                    value={crmExternalIdForCreate}
                    onChange={(e) => setCrmExternalIdForCreate(e.target.value)}
                    placeholder="masalan email@uysot"
                    className="w-full border rounded px-3 py-2 text-sm"
                  />
                </div>
              )}
              <button
                type="submit"
                disabled={submitting}
                className="w-full bg-indigo-600 text-white rounded py-2 text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
              >
                {submitting ? "Yaratilmoqda..." : "Qo'shish"}
              </button>
            </form>

            {lastInviteLink && (
              <div className="mt-4 p-3 bg-emerald-50 border border-emerald-200 rounded text-xs break-all">
                <p className="font-medium text-emerald-700 mb-1">Bot havolasi:</p>
                <a href={lastInviteLink} target="_blank" rel="noreferrer" className="text-emerald-800 underline">
                  {lastInviteLink}
                </a>
              </div>
            )}
          </div>
        )}

        <div className={`${canCreateUser ? "md:col-span-2" : ""} bg-white rounded-lg shadow p-5`}>
          <h2 className="font-semibold mb-4">Barcha foydalanuvchilar</h2>
          {loading ? (
            <p className="text-sm text-slate-500">Yuklanmoqda...</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-slate-500 border-b">
                  <th className="py-2">Ism</th>
                  <th className="py-2">Rol</th>
                  <th className="py-2">Lavozim</th>
                  <th className="py-2">Holat</th>
                  <th className="py-2">Bot</th>
                  {hasFullControl && <th className="py-2">CRM ID</th>}
                  <th className="py-2"></th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id} className={`border-b last:border-0 ${!u.is_active ? "opacity-50" : ""}`}>
                    <td className="py-2">{u.full_name}</td>
                    <td className="py-2">
                      <select
                        value={u.role}
                        disabled={savingRole === u.id}
                        onChange={(e) => handleRoleChange(u.id, e.target.value)}
                        className="border rounded px-2 py-1 text-xs disabled:opacity-50"
                      >
                        {Object.entries(ROLE_LABELS).map(([value, label]) => (
                          <option key={value} value={value}>
                            {label}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="py-2">
                      {canSetPosition ? (
                        <select
                          value={u.position_id ?? ""}
                          disabled={savingPosition === u.id}
                          onChange={(e) => handlePositionChange(u.id, e.target.value)}
                          className="border rounded px-2 py-1 text-xs disabled:opacity-50"
                        >
                          <option value="">— yo'q —</option>
                          {positions.map((p) => (
                            <option key={p.id} value={p.id}>
                              {p.name}
                            </option>
                          ))}
                        </select>
                      ) : (
                        u.position?.name ?? "—"
                      )}
                    </td>
                    <td className="py-2">{u.is_active ? "Faol" : "O'chirilgan"}</td>
                    <td className="py-2">{u.bot_started ? "✅ ulangan" : "— kutilmoqda"}</td>
                    {hasFullControl && (
                      <td className="py-2">
                        <div className="flex items-center gap-2">
                          <input
                            value={crmDrafts[u.id] ?? ""}
                            onChange={(e) => setCrmDrafts((prev) => ({ ...prev, [u.id]: e.target.value }))}
                            placeholder="masalan email@uysot"
                            className="w-40 border rounded px-2 py-1 text-xs"
                          />
                          <button
                            onClick={() => saveCrmExternalId(u.id)}
                            disabled={savingCrmId === u.id}
                            className="text-indigo-600 hover:underline text-xs disabled:opacity-50"
                          >
                            Saqlash
                          </button>
                        </div>
                      </td>
                    )}
                    <td className="py-2 text-right whitespace-nowrap">
                      <div className="flex items-center justify-end gap-3">
                        {!u.bot_started && (
                          <button
                            onClick={() => showInviteLink(u.id)}
                            className="text-indigo-600 hover:underline text-xs"
                          >
                            Havola olish
                          </button>
                        )}
                        {u.bot_started && (
                          <button
                            onClick={() => handleResetAccount(u.id)}
                            className="text-indigo-600 hover:underline text-xs"
                          >
                            Qayta bog'lash
                          </button>
                        )}
                        {u.is_active ? (
                          <button
                            onClick={() => handleDeactivate(u.id)}
                            className="text-red-600 hover:underline text-xs"
                          >
                            O'chirish
                          </button>
                        ) : (
                          <button
                            onClick={() => handleActivate(u.id)}
                            className="text-emerald-600 hover:underline text-xs"
                          >
                            Tiklash
                          </button>
                        )}
                        {hasFullControl && (
                          <button
                            onClick={() => handleDelete(u.id, u.full_name)}
                            disabled={deletingId === u.id}
                            className="text-red-800 hover:underline text-xs font-medium disabled:opacity-50"
                            title={isDasturchi ? "Dasturchi: norma/vazifa borligiga qaramay to'liq o'chiradi" : undefined}
                          >
                            {isDasturchi ? "Majburiy o'chirish" : "Butunlay o'chirish"}
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {hasFullControl && operators.length > 0 && (
        <div className="bg-white rounded-lg shadow p-5">
          <h2 className="font-semibold mb-1">CRM bog'lash</h2>
          <p className="text-xs text-slate-400 mb-4">
            Uysot'da bugun qo'ng'iroq qilgan operatorlar. Har birini qo'lda email yozish o'rniga, ro'yxatdan
            Telegram orqali ulangan foydalanuvchini tanlab bog'lang.
          </p>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 border-b">
                <th className="py-2">Uysot identifikatori</th>
                <th className="py-2">Bugungi qo'ng'iroqlar</th>
                <th className="py-2">Bog'langan foydalanuvchi</th>
                <th className="py-2"></th>
              </tr>
            </thead>
            <tbody>
              {operators.map((op) => (
                <tr key={op.crm_external_id} className="border-b last:border-0">
                  <td className="py-2">{op.crm_external_id}</td>
                  <td className="py-2">{op.calls_today}</td>
                  <td className="py-2">
                    {op.matched_user ? (
                      <span className="text-emerald-700">✅ {op.matched_user.full_name}</span>
                    ) : (
                      <span className="text-slate-400">— bog'lanmagan</span>
                    )}
                  </td>
                  <td className="py-2 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <select
                        value={operatorLinkChoice[op.crm_external_id] ?? ""}
                        onChange={(e) =>
                          setOperatorLinkChoice((prev) => ({ ...prev, [op.crm_external_id]: e.target.value }))
                        }
                        className="border rounded px-2 py-1 text-xs"
                      >
                        <option value="">— foydalanuvchi tanlang —</option>
                        {telegramConnectedUsers.map((u) => (
                          <option key={u.id} value={u.id}>
                            {u.full_name} ({ROLE_LABELS[u.role] ?? u.role})
                          </option>
                        ))}
                      </select>
                      <button
                        onClick={() => handleLinkOperator(op.crm_external_id)}
                        disabled={linkingOperator === op.crm_external_id || !operatorLinkChoice[op.crm_external_id]}
                        className="text-indigo-600 hover:underline text-xs disabled:opacity-50"
                      >
                        Bog'lash
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
