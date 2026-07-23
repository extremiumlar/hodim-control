import { FormEvent, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useCreateUser } from "@/lib/queries";
import { ROLE_LABELS } from "./constants";

/** Yangi foydalanuvchi qo'shish formasi — muvaffaqiyatda bot havolasini chiqaradi. */
export default function UserCreateForm({
  hasFullControl,
  onInviteLink,
}: {
  hasFullControl: boolean;
  onInviteLink: (link: string) => void;
}) {
  const createUser = useCreateUser();
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState("employee");
  const [crmExternalId, setCrmExternalId] = useState("");
  const [isSeat, setIsSeat] = useState(false);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!fullName) return;
    createUser.mutate(
      {
        full_name: fullName,
        role,
        crm_external_id: hasFullControl && crmExternalId ? crmExternalId.trim() : undefined,
        is_seat: isSeat,
      },
      {
        onSuccess: ({ invite_link }) => {
          toast.success("Foydalanuvchi yaratildi");
          onInviteLink(invite_link);
          setFullName("");
          setCrmExternalId("");
          setIsSeat(false);
        },
      }
    );
  };

  return (
    <Card className="h-fit">
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Foydalanuvchi qo'shish</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <Label htmlFor="u-name">To'liq ism</Label>
            <Input id="u-name" value={fullName} onChange={(e) => setFullName(e.target.value)} required />
          </div>
          <div>
            <Label>Rol</Label>
            <Select value={role} onValueChange={setRole}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(ROLE_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {role === "employee" && (
              <p className="mt-1 text-xs text-amber-600">
                Eslatma: yaratilgandan keyin xodimga lavozim (yoki ROP rahbar) biriktiring —
                biriktirilmaguncha uni zaxira qoida bo'yicha HR boshqaradi.
              </p>
            )}
          </div>
          {hasFullControl && (
            <div>
              <Label htmlFor="u-crm">CRM ID (ixtiyoriy)</Label>
              <Input
                id="u-crm"
                value={crmExternalId}
                onChange={(e) => setCrmExternalId(e.target.value)}
                placeholder="masalan email@uysot"
              />
            </div>
          )}
          <label className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={isSeat}
              onChange={(e) => setIsSeat(e.target.checked)}
            />
            <span>
              Almashinuvchi o'rin (masalan Mobilogrof) — havola doimiy qayta olinadi, boshqa
              odam shu havola orqali /start bossa joriy egasi almashadi.
            </span>
          </label>
          <Button type="submit" disabled={createUser.isPending} className="w-full">
            {createUser.isPending ? "Yaratilmoqda..." : "Qo'shish"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
