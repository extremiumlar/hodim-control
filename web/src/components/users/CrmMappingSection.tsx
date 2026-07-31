import { useEffect, useState } from "react";
import { toast } from "sonner";
import { MobileCard, MobileCardRow } from "@/components/MobileCard";
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
    // `min-w-0` — flex bolasining sukut `min-width: auto` qiymati <select>ni eng
    // uzun variantdan tor bo'lishga qo'ymaydi va 360 px ekranda butun sahifani
    // gorizontal scrollga tushiradi (Users.tsx grid'idagi bilan bir xil nuqson).
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="min-w-0 rounded border px-2 py-1 text-xs"
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

type MappingRow = {
  id: string;
  /** Uysot identifikatori (qo'ng'iroq) yoki Uysot'dagi ism (tashrif) */
  ident: string;
  /** Bugungi qo'ng'iroqlar yoki tashriflar soni */
  count: number;
  matched: User | null;
  suggested: User | null;
};

/**
 * Ikkala bog'lash bo'limi (qo'ng'iroq va tashrif) tuzilishi bir xil — 4 ustun,
 * oxirgisida tanlov+tugma. Shuning uchun bitta komponent: aks holda ustun yoki
 * mobil ko'rinish o'zgarganda ikki joyni qo'lda moslash kerak bo'lardi.
 */
function MappingCard({
  title,
  description,
  identLabel,
  countLabel,
  rows,
  users,
  choice,
  onChoiceChange,
  isPending,
  onLink,
}: {
  title: string;
  description: string;
  identLabel: string;
  countLabel: string;
  rows: MappingRow[];
  users: User[];
  choice: Record<string, string>;
  onChoiceChange: (id: string, value: string) => void;
  isPending: boolean;
  onLink: (id: string, userId: number) => void;
}) {
  const linkButton = (row: MappingRow) => (
    <Button
      variant="link"
      size="sm"
      className="h-7 shrink-0 px-1 text-xs"
      disabled={isPending || !choice[row.id]}
      onClick={() => onLink(row.id, Number(choice[row.id]))}
    >
      Bog'lash
    </Button>
  );

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="mb-4 text-xs text-slate-400">{description}</p>

        {/* ── Telefon (md dan kichik): karta ko'rinishi ──
            Ilgari bu yerda faqat jadval bor edi va 360 px ekranda 465 px
            yashirin gorizontal scroll berardi (shadcn `Table` o'zining
            `overflow-auto` wrapper'i ichida). */}
        <div className="space-y-2 md:hidden">
          {rows.map((row) => (
            <MobileCard key={row.id}>
              <MobileCardRow label={identLabel}>{row.ident}</MobileCardRow>
              <MobileCardRow label={countLabel}>{row.count}</MobileCardRow>
              <MobileCardRow label="Bog'langan foydalanuvchi">
                <MatchCell matched={row.matched} suggested={row.suggested} />
              </MobileCardRow>
              <MobileCardRow>
                <div className="flex items-center justify-between gap-2">
                  <UserSelect
                    value={choice[row.id] ?? ""}
                    onChange={(v) => onChoiceChange(row.id, v)}
                    users={users}
                  />
                  {linkButton(row)}
                </div>
              </MobileCardRow>
            </MobileCard>
          ))}
        </div>

        {/* ── Desktop (md va yuqori): jadval ── */}
        <div className="hidden md:block">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{identLabel}</TableHead>
                <TableHead>{countLabel}</TableHead>
                <TableHead>Bog'langan foydalanuvchi</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.id}>
                  <TableCell>{row.ident}</TableCell>
                  <TableCell>{row.count}</TableCell>
                  <TableCell>
                    <MatchCell matched={row.matched} suggested={row.suggested} />
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-2">
                      <UserSelect
                        value={choice[row.id] ?? ""}
                        onChange={(v) => onChoiceChange(row.id, v)}
                        users={users}
                      />
                      {linkButton(row)}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
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
        <MappingCard
          title="CRM bog'lash"
          description="Uysot'da bugun qo'ng'iroq qilgan operatorlar. Har birini qo'lda email yozish o'rniga, ro'yxatdan Telegram orqali ulangan foydalanuvchini tanlab bog'lang."
          identLabel="Uysot identifikatori"
          countLabel="Bugungi qo'ng'iroqlar"
          rows={operators.map((op) => ({
            id: op.crm_external_id,
            ident: op.crm_external_id,
            count: op.calls_today,
            matched: op.matched_user,
            suggested: op.suggested_user,
          }))}
          users={telegramConnectedUsers}
          choice={callChoice}
          onChoiceChange={(id, v) => setCallChoice((prev) => ({ ...prev, [id]: v }))}
          isPending={linkCall.isPending}
          onLink={(id, userId) =>
            linkCall.mutate(
              { userId, crmExternalId: id },
              { onSuccess: () => toast.success("Bog'landi") }
            )
          }
        />
      )}

      {visitOperators.length > 0 && (
        <MappingCard
          title="Tashrif bog'lash"
          description={
            'Uysot\'da bugun "Tashrif" bosqichida qayd etilgan javobgarlar — bu yerda Uysot email ' +
            "emas, ISM (Uysot'dagi javobgar ismi) beradi. Mos keladigan foydalanuvchi topilsa, " +
            'avtomatik taklif qilinadi — tasdiqlab "Bog\'lash"ni bosing (yoki boshqasini tanlang).'
          }
          identLabel="Uysot'dagi ism"
          countLabel="Bugungi tashriflar"
          rows={visitOperators.map((op) => ({
            id: op.responsible_id,
            ident: op.responsible_name,
            count: op.visits_today,
            matched: op.matched_user,
            suggested: op.suggested_user,
          }))}
          users={telegramConnectedUsers}
          choice={visitChoice}
          onChoiceChange={(id, v) => setVisitChoice((prev) => ({ ...prev, [id]: v }))}
          isPending={linkVisit.isPending}
          onLink={(id, userId) =>
            linkVisit.mutate(
              { userId, crmVisitExternalId: id },
              { onSuccess: () => toast.success("Bog'landi") }
            )
          }
        />
      )}
    </>
  );
}
