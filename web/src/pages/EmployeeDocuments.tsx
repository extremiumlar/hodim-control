/**
 * «Kadr hujjatlari» — HR paneli (TZ 3.4 / S-11).
 *
 * Xodim tanlanadi → uning hujjatlari ko'rinadi. Yuklash BOTDA
 * («📎 Hujjat yuklash»): fayl Telegram'ga tushishi kerak, brauzerdan
 * yuklash esa faylni avval serverga olib kelardi — disk kvotasi tor
 * (1 GB) va TZ 1.1 buni taqiqlaydi.
 *
 * ⚠️ ROP bu sahifani KO'RMAYDI (`can_view_hr_docs`) va backend ham
 * unga 404 beradi — ko'rinishni yashirish yetarli emas.
 */
import { useState } from "react";
import { FolderArchive } from "lucide-react";

import PageHeader from "@/components/PageHeader";
import DocumentList from "@/components/documents/DocumentList";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useUserDocuments, useUsers } from "@/lib/queries";

export default function EmployeeDocuments() {
  const { data: users } = useUsers();
  const [userId, setUserId] = useState<number | null>(null);
  const { data, isLoading } = useUserDocuments(userId);

  return (
    <div className="space-y-4">
      <PageHeader title="Kadr hujjatlari" />

      <div className="rounded-lg border border-sky-200 bg-sky-50 p-3 text-xs text-sky-900">
        Hujjat <b>botdan</b> yuklanadi: «📎 Hujjat yuklash» → xodim → tur →
        fayl. Fayl Telegram'da qoladi, serverda joy egallamaydi. Izohga
        <code className="mx-1">2027-12-31</code> ko'rinishida sana yozsangiz —
        amal muddati shundan olinadi.
      </div>

      <Card>
        <CardHeader className="flex-row items-center justify-between gap-2 pb-3">
          <CardTitle className="text-base">Xodim hujjatlari</CardTitle>
          <Select
            value={userId ? String(userId) : ""}
            onValueChange={(v) => setUserId(Number(v))}
          >
            <SelectTrigger className="w-64">
              <SelectValue placeholder="Xodimni tanlang" />
            </SelectTrigger>
            <SelectContent>
              {(users ?? []).map((u) => (
                <SelectItem key={u.id} value={String(u.id)}>
                  {u.full_name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </CardHeader>
        <CardContent>
          {userId === null ? (
            <div className="flex items-center gap-2 rounded-lg border border-dashed p-4 text-sm text-slate-600">
              <FolderArchive className="h-4 w-4 shrink-0" />
              Hujjatlarni ko'rish uchun xodimni tanlang.
            </div>
          ) : (
            <DocumentList
              documents={data}
              isLoading={isLoading}
              canManage
              emptyText="Bu xodimda hali hujjat yo'q."
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
