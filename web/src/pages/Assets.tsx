/**
 * «Mol-mulk» — HR paneli (TZ 3.11 / S-18).
 *
 * Noutbuk, telefon, SIM-karta va asbob kimdaligi hech qayerda yozilmagan
 * edi. Xodim ishdan bo'shaganda «unda nima bor edi?» degan savolga javob
 * yo'q va buyum shunchaki yo'qolardi.
 *
 * ⚠️ Band buyumni ikkinchi xodimga biriktirib bo'lmaydi — backend 409
 * beradi va kimda ekanini aytadi. Interfeys ham band buyumda biriktirish
 * tugmasini ko'rsatmaydi, lekin haqiqiy to'siq serverda.
 */
import { useState } from "react";
import { FileDown, History, ListChecks, Package, PackageCheck, PackageX } from "lucide-react";
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
import {
  useAddAsset,
  useAssetAct,
  useAssetHistory,
  useAssetKinds,
  useAssetStandardSet,
  useAssets,
  useAssignAsset,
  useDocumentTemplates,
  usePositions,
  useReturnAsset,
  useSetAssetStandardSet,
  useUsers,
} from "@/lib/queries";

function pul(n: number | null): string {
  return n === null ? "—" : `${n.toLocaleString("ru-RU").replace(/ /g, " ")} so'm`;
}

export default function Assets() {
  const { data, isLoading } = useAssets();
  const { data: meta } = useAssetKinds();
  const { data: users } = useUsers();
  const { data: positions } = usePositions();
  const { data: templates } = useDocumentTemplates();
  const add = useAddAsset();
  const assign = useAssignAsset();
  const ret = useReturnAsset();
  const act = useAssetAct();

  //  Dalolatnoma shabloni: «Dalolatnoma» turidagilar (S-14 da yuklanadi).
  const [tmplId, setTmplId] = useState("");
  const actTemplates = (templates ?? []).filter((t) => t.kind === "act");

  //  Standart to'plam muharriri (S-19).
  const [posId, setPosId] = useState<number | null>(null);
  const { data: stdSet } = useAssetStandardSet(posId);
  const saveSet = useSetAssetStandardSet();
  const [draft, setDraft] = useState<Record<string, number> | null>(null);
  //  Serverdan kelgan to'plam — muharrir hali ochilmagan bo'lsa shundan.
  const current: Record<string, number> =
    draft ?? Object.fromEntries((stdSet?.items ?? []).map((i) => [i.kind, i.quantity]));

  const [inv, setInv] = useState("");
  const [name, setName] = useState("");
  const [kind, setKind] = useState("");
  const [value, setValue] = useState("");

  //  Biriktirish uchun har buyumda tanlangan xodim.
  const [pick, setPick] = useState<Record<number, string>>({});
  const [openHistory, setOpenHistory] = useState<number | null>(null);
  const { data: hist } = useAssetHistory(openHistory);

  async function qosh() {
    if (!inv.trim() || !name.trim() || !kind) {
      toast.error("Inventar raqami, nomi va turini kiriting");
      return;
    }
    await add.mutateAsync({
      inventory_no: inv.trim(),
      name: name.trim(),
      kind,
      value: value ? Number(value.replace(/\s/g, "")) : null,
    });
    toast.success("Buyum qo'shildi");
    setInv("");
    setName("");
    setValue("");
  }

  const band = (data ?? []).filter((a) => a.holder_id !== null).length;

  return (
    <div className="space-y-4">
      <PageHeader title="Mol-mulk" />

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Package className="h-4 w-4" />
            Yangi buyum
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap items-end gap-2">
          <div className="w-40">
            <div className="mb-1 text-xs text-slate-600">Inventar raqami</div>
            <Input value={inv} onChange={(e) => setInv(e.target.value)} placeholder="INV-001" />
          </div>
          <div className="min-w-[200px] flex-1">
            <div className="mb-1 text-xs text-slate-600">Nomi</div>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="min-w-[170px]">
            <div className="mb-1 text-xs text-slate-600">Turi</div>
            <Select value={kind} onValueChange={setKind}>
              <SelectTrigger>
                <SelectValue placeholder="Tanlang" />
              </SelectTrigger>
              <SelectContent>
                {(meta?.kinds ?? []).map((k) => (
                  <SelectItem key={k.value} value={k.value}>
                    {k.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="w-36">
            <div className="mb-1 text-xs text-slate-600">Qiymati</div>
            <Input
              value={value}
              inputMode="numeric"
              onChange={(e) => setValue(e.target.value)}
            />
          </div>
          <Button onClick={qosh} disabled={add.isPending}>
            Qo'shish
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex-row items-center justify-between gap-2 pb-3">
          <CardTitle className="text-base">Buyumlar</CardTitle>
          <div className="flex items-center gap-2">
            {actTemplates.length > 0 && (
              <Select value={tmplId} onValueChange={setTmplId}>
                <SelectTrigger className="h-8 w-52 text-xs">
                  <SelectValue placeholder="Dalolatnoma shabloni" />
                </SelectTrigger>
                <SelectContent>
                  {actTemplates.map((t) => (
                    <SelectItem key={t.id} value={String(t.id)}>
                      {t.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            <span className="text-xs text-slate-600">
              {data?.length ?? 0} ta · {band} tasi xodimlarda
            </span>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <Skeleton className="h-32 w-full" />
          ) : !data?.length ? (
            <div className="rounded-lg border border-dashed p-4 text-sm text-slate-600">
              Hali buyum kiritilmagan.
            </div>
          ) : (
            <ul className="divide-y">
              {data.map((a) => (
                <li key={a.id} className="py-2.5 text-sm">
                  <div className="flex flex-wrap items-center gap-3">
                    <span className="w-24 shrink-0 font-mono text-xs text-slate-600">
                      {a.inventory_no}
                    </span>
                    <span className="min-w-[140px] flex-1">
                      <span className="block truncate font-medium">{a.name}</span>
                      <span className="block text-xs text-slate-600">
                        {a.kind_label} · {a.condition_label} · {pul(a.value)}
                      </span>
                    </span>

                    {a.holder_id ? (
                      <>
                        <span className="flex shrink-0 items-center gap-1 rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-900">
                          <PackageCheck className="h-3.5 w-3.5" />
                          {a.holder_name}
                          {a.accepted ? "" : " (tasdiqlamagan)"}
                        </span>
                        <span className="shrink-0 font-mono text-xs text-slate-500">
                          {a.assigned_at}
                        </span>
                        <Button
                          size="sm"
                          variant="outline"
                          className="shrink-0"
                          disabled={ret.isPending}
                          onClick={async () => {
                            await ret.mutateAsync({ id: a.id, condition_in: a.condition });
                            toast.success(`«${a.name}» qaytarib olindi`);
                          }}
                        >
                          <PackageX className="mr-1 h-3.5 w-3.5" />
                          Qaytarish
                        </Button>
                      </>
                    ) : (
                      <>
                        <span className="shrink-0 rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                          omborda
                        </span>
                        <Select
                          value={pick[a.id] ?? ""}
                          onValueChange={(v) => setPick((p) => ({ ...p, [a.id]: v }))}
                        >
                          <SelectTrigger className="h-8 w-48 shrink-0 text-xs">
                            <SelectValue placeholder="Kimga berish" />
                          </SelectTrigger>
                          <SelectContent>
                            {(users ?? []).map((u) => (
                              <SelectItem key={u.id} value={String(u.id)}>
                                {u.full_name}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        <Button
                          size="sm"
                          className="shrink-0"
                          disabled={!pick[a.id] || assign.isPending}
                          onClick={async () => {
                            await assign.mutateAsync({
                              id: a.id,
                              user_id: Number(pick[a.id]),
                              condition_out: a.condition,
                            });
                            toast.success(`«${a.name}» biriktirildi`);
                            setPick((p) => ({ ...p, [a.id]: "" }));
                          }}
                        >
                          Biriktirish
                        </Button>
                      </>
                    )}

                    {tmplId && (
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-7 w-7 shrink-0"
                        title={
                          a.holder_id
                            ? "Biriktirish dalolatnomasi"
                            : "Qaytarish dalolatnomasi"
                        }
                        disabled={act.isPending}
                        onClick={async () => {
                          const r = await act.mutateAsync({
                            id: a.id,
                            template_id: Number(tmplId),
                            action: a.holder_id ? "out" : "in",
                          });
                          toast.success(
                            r.missing?.length
                              ? `Navbatga qo'yildi. To'ldirilmaydi: ${r.missing.join(", ")}`
                              : "Dalolatnoma navbatga qo'yildi — Telegram'ga keladi"
                          );
                        }}
                      >
                        <FileDown className="h-3.5 w-3.5" />
                      </Button>
                    )}
                    <Button
                      size="icon"
                      variant="ghost"
                      className="h-7 w-7 shrink-0"
                      title="Tarix"
                      onClick={() => setOpenHistory(openHistory === a.id ? null : a.id)}
                    >
                      <History className="h-3.5 w-3.5" />
                    </Button>
                  </div>

                  {openHistory === a.id && (
                    <div className="mt-2 rounded-lg border bg-slate-50 p-2 text-xs">
                      {!hist?.length ? (
                        <span className="text-slate-600">Tarix bo'sh.</span>
                      ) : (
                        <ul className="space-y-1">
                          {hist.map((h) => (
                            <li key={h.id} className="flex flex-wrap gap-2">
                              <span className="font-medium">{h.user_name}</span>
                              <span className="text-slate-600">
                                {h.assigned_at} → {h.returned_at ?? "hozir"}
                              </span>
                              {h.condition_in && h.condition_in !== h.condition_out && (
                                <span className="text-rose-700">
                                  holat: {h.condition_out} → {h.condition_in}
                                </span>
                              )}
                              {h.accepted_at && (
                                <span className="text-emerald-700">qabul qilgan</span>
                              )}
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

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <ListChecks className="h-4 w-4" />
            Lavozimga standart to'plam
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-xs text-slate-600">
            Yangi xodim kelganda unga nima berish kerakligi va ishdan
            bo'shaganda nima qaytarilishi kerakligi shu ro'yxatdan olinadi.
            Bu yerda <b>tur</b> belgilanadi, aniq buyumni biriktirish paytida
            tanlaysiz.
          </p>
          <Select
            value={posId ? String(posId) : ""}
            onValueChange={(v) => {
              setPosId(Number(v));
              setDraft(null);
            }}
          >
            <SelectTrigger className="w-64">
              <SelectValue placeholder="Lavozimni tanlang" />
            </SelectTrigger>
            <SelectContent>
              {(positions ?? []).map((p) => (
                <SelectItem key={p.id} value={String(p.id)}>
                  {p.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {posId !== null && (
            <>
              <div className="flex flex-wrap gap-2">
                {(meta?.kinds ?? []).map((k) => (
                  <label
                    key={k.value}
                    className="flex items-center gap-2 rounded-lg border px-2 py-1 text-xs"
                  >
                    <input
                      type="checkbox"
                      className="h-3.5 w-3.5"
                      checked={(current[k.value] ?? 0) > 0}
                      onChange={(e) =>
                        setDraft((d) => {
                          const base = d ?? current;
                          const next = { ...base };
                          if (e.target.checked) next[k.value] = 1;
                          else delete next[k.value];
                          return next;
                        })
                      }
                    />
                    {k.label}
                    {(current[k.value] ?? 0) > 0 && (
                      <Input
                        value={String(current[k.value])}
                        inputMode="numeric"
                        className="h-6 w-12 px-1 text-center text-xs"
                        onChange={(e) =>
                          setDraft((d) => ({
                            ...(d ?? current),
                            [k.value]: Math.max(1, Number(e.target.value) || 1),
                          }))
                        }
                      />
                    )}
                  </label>
                ))}
              </div>
              <Button
                size="sm"
                disabled={saveSet.isPending}
                onClick={async () => {
                  await saveSet.mutateAsync({
                    position_id: posId,
                    items: current,
                  });
                  setDraft(null);
                  toast.success("To'plam saqlandi");
                }}
              >
                Saqlash
              </Button>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
