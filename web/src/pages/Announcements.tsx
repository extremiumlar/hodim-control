/**
 * «E'lonlar» — rahbar paneli (TZ 3.12 / S-21).
 *
 * ⚠️ KUNLIK LIMIT ko'rinib turadi. Cheklovsiz tizim e'lon spamiga
 * aylanadi: kuniga o'nta xabar kelsa xodim ularni o'qimay yopib qo'yadi
 * va MUHIM e'lon ham shu taqdirni ko'radi.
 *
 * Muhim e'londa kim o'qigani/o'qimagani ko'rinadi (`acknowledgements`,
 * S-20). O'qimaganlar tepada — rahbarga aynan ular kerak.
 */
import { useState } from "react";
import { AlertTriangle, Eye, Megaphone, Trash2 } from "lucide-react";
import { toast } from "sonner";

import PageHeader from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  useAckReaders,
  useAddAnnouncement,
  useAnnouncementQuota,
  useAnnouncements,
  useDeleteAnnouncement,
  usePositions,
} from "@/lib/queries";

const QAMROVLAR = [
  { value: "all", label: "Hamma" },
  { value: "roles", label: "Rol bo'yicha" },
  { value: "positions", label: "Lavozim bo'yicha" },
];

const ROLLAR = ["employee", "rop", "hr", "boss", "dasturchi"];

export default function Announcements() {
  const { data, isLoading } = useAnnouncements();
  const { data: quota } = useAnnouncementQuota();
  const { data: positions } = usePositions();
  const add = useAddAnnouncement();
  const del = useDeleteAnnouncement();

  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [audience, setAudience] = useState("all");
  const [scope, setScope] = useState<string[]>([]);
  const [important, setImportant] = useState(false);
  const [openReaders, setOpenReaders] = useState<number | null>(null);

  const current = (data ?? []).find((a) => a.id === openReaders);
  const { data: readers } = useAckReaders(
    openReaders === null ? null : "announcement",
    openReaders,
    current?.version
  );

  const tugadi = (quota?.left ?? 1) <= 0;

  async function yubor() {
    if (!title.trim() || !body.trim()) {
      toast.error("Sarlavha va matnni kiriting");
      return;
    }
    if (audience !== "all" && scope.length === 0) {
      toast.error("Qamrov tanlangan, lekin ro'yxat bo'sh");
      return;
    }
    const r = await add.mutateAsync({
      title: title.trim(),
      body: body.trim(),
      audience,
      scope_ids: audience === "all" ? null : scope,
      important,
    });
    toast.success(
      `${r.audience_size} xodimga yuborildi` +
        (r.ack_requested ? ", tanishish so'raldi" : "") +
        `. Bugun yana ${r.left_today} ta mumkin.`
    );
    setTitle("");
    setBody("");
    setScope([]);
    setImportant(false);
  }

  return (
    <div className="space-y-4">
      <PageHeader title="E'lonlar" />

      {quota && (
        <div
          className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-xs ${
            tugadi
              ? "border-rose-200 bg-rose-50 text-rose-900"
              : "border-slate-200 bg-slate-50 text-slate-700"
          }`}
        >
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
          Bugun {quota.sent_today}/{quota.daily_limit} e'lon yuborilgan
          {tugadi
            ? " — chegara to'ldi. Kuniga ko'p e'lon kelsa xodimlar ularni o'qimay qo'yadi."
            : `. Yana ${quota.left} ta mumkin.`}
        </div>
      )}

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Megaphone className="h-4 w-4" />
            Yangi e'lon
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <Input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Sarlavha"
          />
          <Textarea
            rows={4}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder="E'lon matni"
          />
          <div className="flex flex-wrap items-center gap-2">
            <Select
              value={audience}
              onValueChange={(v) => {
                setAudience(v);
                setScope([]);
              }}
            >
              <SelectTrigger className="w-44">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {QAMROVLAR.map((q) => (
                  <SelectItem key={q.value} value={q.value}>
                    {q.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            {audience === "roles" &&
              ROLLAR.map((r) => (
                <label key={r} className="flex items-center gap-1 text-xs">
                  <input
                    type="checkbox"
                    className="h-3.5 w-3.5"
                    checked={scope.includes(r)}
                    onChange={(e) =>
                      setScope((s) => (e.target.checked ? [...s, r] : s.filter((x) => x !== r)))
                    }
                  />
                  {r}
                </label>
              ))}
            {audience === "positions" &&
              (positions ?? []).map((p) => (
                <label key={p.id} className="flex items-center gap-1 text-xs">
                  <input
                    type="checkbox"
                    className="h-3.5 w-3.5"
                    checked={scope.includes(String(p.id))}
                    onChange={(e) =>
                      setScope((s) =>
                        e.target.checked
                          ? [...s, String(p.id)]
                          : s.filter((x) => x !== String(p.id))
                      )
                    }
                  />
                  {p.name}
                </label>
              ))}

            <label className="ml-auto flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="h-4 w-4"
                checked={important}
                onChange={(e) => setImportant(e.target.checked)}
              />
              Muhim («Tanishdim» talab qilinadi)
            </label>
            <Button onClick={yubor} disabled={add.isPending || tugadi}>
              Yuborish
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Yuborilgan e'lonlar</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <Skeleton className="h-24 w-full" />
          ) : !data?.length ? (
            <div className="rounded-lg border border-dashed p-4 text-sm text-slate-600">
              Hali e'lon yuborilmagan.
            </div>
          ) : (
            <ul className="divide-y">
              {data.map((a) => (
                <li key={a.id} className="py-2.5 text-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    {a.important && (
                      <span className="shrink-0 rounded bg-rose-100 px-1.5 py-0.5 text-xs text-rose-800">
                        Muhim
                      </span>
                    )}
                    <span className="min-w-0 flex-1 truncate font-medium">{a.title}</span>
                    <span className="shrink-0 text-xs text-slate-500">
                      {a.audience === "all" ? "hamma" : a.audience}
                      {a.version > 1 ? ` · v${a.version}` : ""}
                    </span>
                    {a.important && (
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-7 w-7 shrink-0"
                        title="Kim o'qigan"
                        onClick={() => setOpenReaders(openReaders === a.id ? null : a.id)}
                      >
                        <Eye className="h-3.5 w-3.5" />
                      </Button>
                    )}
                    <Button
                      size="icon"
                      variant="ghost"
                      className="h-7 w-7 shrink-0"
                      disabled={del.isPending}
                      onClick={async () => {
                        await del.mutateAsync(a.id);
                        toast.success("O'chirildi");
                      }}
                    >
                      <Trash2 className="h-3.5 w-3.5 text-rose-600" />
                    </Button>
                  </div>

                  {openReaders === a.id && (
                    <div className="mt-2 rounded-lg border bg-slate-50 p-2 text-xs">
                      {!readers?.length ? (
                        <span className="text-slate-600">Ma'lumot yo'q.</span>
                      ) : (
                        <ul className="space-y-0.5">
                          {readers.map((r) => (
                            <li key={r.user_id} className="flex gap-2">
                              <span
                                className={
                                  r.acknowledged_at ? "text-emerald-700" : "text-rose-700"
                                }
                              >
                                {r.acknowledged_at ? "✓" : "○"}
                              </span>
                              <span>{r.user_name}</span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
