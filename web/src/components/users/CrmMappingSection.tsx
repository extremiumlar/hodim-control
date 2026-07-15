import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { type User } from "@/lib/api";
import {
  useCrmOperators,
  useCrmVisitOperators,
  useUpdateCrmExternalId,
  useUpdateCrmVisitExternalId,
  useUsers,
} from "@/lib/queries";
import { ROLE_LABELS } from "./constants";

function MatchCell({ matched, suggested }: { matched: User | null; suggested: User | null }) {
  if (matched) return <span className="text-emerald-700">✅ {matched.full_name}</span>;
  if (suggested) return <span className="text-amber-600">taklif: {suggested.full_name}</span>;
  return <span className="text-slate-400">— bog'lanmagan</span>;
}

function UserSelect({
  value,
  onChange,
  users,
}: {
  value: string;
  onChange: (v: string) => void;
  users: User[];
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="rounded border px-2 py-1 text-xs"
    >
      <option value="">— foydalanuvchi tanlang —</option>
      {users.map((u) => (
        <option key={u.id} value={u.id}>
          {u.full_name} ({ROLE_LABELS[u.role] ?? u.role})
        </option>
      ))}
    </select>
  );
}

/**
 * CRM bog'lash bo'limlari (faqat boss/dasturchi): Uysot qo'ng'iroq operatorlarini
 * va "Tashrif" javobgarlarini tizim foydalanuvchilariga bog'lash.
 */
export default function CrmMappingSection() {
  const usersQuery = useUsers(undefined, true);
  const operatorsQuery = useCrmOperators();
  const visitsQuery = useCrmVisitOperators();
  const linkCall = useUpdateCrmExternalId();
  const linkVisit = useUpdateCrmVisitExternalId();

  const [callChoice, setCallChoice] = useState<Record<string, string>>({});
  const [visitChoice, setVisitChoice] = useState<Record<string, string>>({});

  const telegramConnectedUsers = (usersQuery.data ?? []).filter((u) => u.bot_started);

  // Taklif qilingan (ism bo'yicha eng yaqin) foydalanuvchini oldindan tanlab qo'yamiz —
  // boss faqat tasdiqlashi kifoya, lekin xohlasa boshqasini tanlashi ham mumkin.
  useEffect(() => {
    if (!operatorsQuery.data) return;
    setCallChoice((prev) => {
      const next = { ...prev };
      operatorsQuery.data.forEach((op) => {
        if (!next[op.crm_external_id] && op.suggested_user) {
          next[op.crm_external_id] = String(op.suggested_user.id);
        }
      });
      return next;
    });
  }, [operatorsQuery.data]);

  useEffect(() => {
    if (!visitsQuery.data) return;
    setVisitChoice((prev) => {
      const next = { ...prev };
      visitsQuery.data.forEach((op) => {
        if (!next[op.responsible_id] && op.suggested_user) {
          next[op.responsible_id] = String(op.suggested_user.id);
        }
      });
      return next;
    });
  }, [visitsQuery.data]);

  const operators = operatorsQuery.data ?? [];
  const visitOperators = visitsQuery.data ?? [];

  return (
    <>
      {operators.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">CRM bog'lash</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="mb-4 text-xs text-slate-400">
              Uysot'da bugun qo'ng'iroq qilgan operatorlar. Har birini qo'lda email yozish o'rniga,
              ro'yxatdan Telegram orqali ulangan foydalanuvchini tanlab bog'lang.
            </p>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Uysot identifikatori</TableHead>
                  <TableHead>Bugungi qo'ng'iroqlar</TableHead>
                  <TableHead>Bog'langan foydalanuvchi</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {operators.map((op) => (
                  <TableRow key={op.crm_external_id}>
                    <TableCell>{op.crm_external_id}</TableCell>
                    <TableCell>{op.calls_today}</TableCell>
                    <TableCell>
                      <MatchCell matched={op.matched_user} suggested={op.suggested_user} />
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-2">
                        <UserSelect
                          value={callChoice[op.crm_external_id] ?? ""}
                          onChange={(v) =>
                            setCallChoice((prev) => ({ ...prev, [op.crm_external_id]: v }))
                          }
                          users={telegramConnectedUsers}
                        />
                        <Button
                          variant="link"
                          size="sm"
                          className="h-7 px-1 text-xs"
                          disabled={linkCall.isPending || !callChoice[op.crm_external_id]}
                          onClick={() =>
                            linkCall.mutate(
                              {
                                userId: Number(callChoice[op.crm_external_id]),
                                crmExternalId: op.crm_external_id,
                              },
                              { onSuccess: () => toast.success("Bog'landi") }
                            )
                          }
                        >
                          Bog'lash
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {visitOperators.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Tashrif bog'lash</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="mb-4 text-xs text-slate-400">
              Uysot'da bugun "Tashrif" bosqichida qayd etilgan javobgarlar — bu yerda Uysot email
              emas, ISM (Uysot'dagi javobgar ismi) beradi. Mos keladigan foydalanuvchi topilsa,
              avtomatik taklif qilinadi — tasdiqlab "Bog'lash"ni bosing (yoki boshqasini tanlang).
            </p>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Uysot'dagi ism</TableHead>
                  <TableHead>Bugungi tashriflar</TableHead>
                  <TableHead>Bog'langan foydalanuvchi</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {visitOperators.map((op) => (
                  <TableRow key={op.responsible_id}>
                    <TableCell>{op.responsible_name}</TableCell>
                    <TableCell>{op.visits_today}</TableCell>
                    <TableCell>
                      <MatchCell matched={op.matched_user} suggested={op.suggested_user} />
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-2">
                        <UserSelect
                          value={visitChoice[op.responsible_id] ?? ""}
                          onChange={(v) =>
                            setVisitChoice((prev) => ({ ...prev, [op.responsible_id]: v }))
                          }
                          users={telegramConnectedUsers}
                        />
                        <Button
                          variant="link"
                          size="sm"
                          className="h-7 px-1 text-xs"
                          disabled={linkVisit.isPending || !visitChoice[op.responsible_id]}
                          onClick={() =>
                            linkVisit.mutate(
                              {
                                userId: Number(visitChoice[op.responsible_id]),
                                crmVisitExternalId: op.responsible_id,
                              },
                              { onSuccess: () => toast.success("Bog'landi") }
                            )
                          }
                        >
                          Bog'lash
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </>
  );
}
