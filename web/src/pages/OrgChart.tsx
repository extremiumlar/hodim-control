/**
 * «Tashkiliy tuzilma» — HR/rahbar (TZ 3.16 / S-40).
 *
 * ⚠️ SXEMANI BRAUZER CHIZADI. Server faqat `nodes` + `parent_id`
 * beradi; rasm SERVERDA yaratilmaydi — rasm generatsiyasi Passenger
 * ishchisini band qilardi va konkurentlik = 1 bo'lgani uchun butun
 * sayt kutib turardi.
 *
 * ⚠️ Og'ir kutubxona OLINMAYDI (TZ: 20–30 tugun). Daraxt oddiy
 * ichma-ich `<ul>` bilan chiziladi — bu mobil ekranda ham o'zidan
 * o'zi ro'yxatga aylanadi va alohida ko'rinish yozish shart emas.
 */
import { useMemo, useState } from "react";
import { AlertTriangle, BellOff, ChevronRight, Network, Plus, UserX } from "lucide-react";
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
import type { OrgNode } from "@/lib/api/types";
import {
  useInstructionAcks,
  useOrgAddDescription,
  useOrgChart,
  useOrgDescriptions,
  useOrgPosition,
  useOrgProfile,
  useOrgSaveProfile,
  useOrgSetParent,
} from "@/lib/queries";

const YOQ = "__none__";

/** Bitta tugun va uning bolalari — REKURSIV.
 *  Halqa backendda to'silgan (`org.assert_no_cycle`), shuning uchun
 *  bu yerda cheksiz chuqurlik xavfi yo'q. */
function Tugun({
  node,
  bolalar,
  onSelect,
  tanlangan,
  daraja,
}: {
  node: OrgNode;
  bolalar: Map<number | null, OrgNode[]>;
  onSelect: (id: number) => void;
  tanlangan: number | null;
  daraja: number;
}) {
  const ichki = bolalar.get(node.id) ?? [];
  const bosh = node.units - node.employees;
  return (
    <li>
      <button
        onClick={() => onSelect(node.id)}
        className={`mb-1 flex w-full flex-wrap items-center gap-2 rounded border px-2 py-1.5 text-left text-sm hover:bg-slate-50 ${
          tanlangan === node.id ? "border-slate-800 bg-slate-50" : ""
        }`}
      >
        {daraja > 0 && <ChevronRight className="h-3.5 w-3.5 shrink-0 text-slate-400" />}
        <span className="font-medium">{node.name}</span>
        <span className="text-xs text-slate-600">
          {node.employees} xodim
          {node.units > 0 && ` / ${node.units} o'rin`}
        </span>
        {bosh > 0 && (
          <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-900">
            {bosh} bo'sh
          </span>
        )}
        {bosh < 0 && (
          <span className="rounded bg-rose-100 px-1.5 py-0.5 text-xs text-rose-900">
            shtatdan {-bosh} ortiq
          </span>
        )}
        {!node.has_description && (
          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">
            yo'riqnomasiz
          </span>
        )}
      </button>
      {!!ichki.length && (
        <ul className="ml-4 border-l pl-3">
          {ichki.map((c) => (
            <Tugun
              key={c.id}
              node={c}
              bolalar={bolalar}
              onSelect={onSelect}
              tanlangan={tanlangan}
              daraja={daraja + 1}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

/**
 * Yo'riqnoma tanishuvi — HR paneli (TZ 3.16 / S-42).
 *
 * ⚠️ `exhausted` — bot 3 marta eslatib bo'ldi va endi JIM. Aynan
 * shu odamlar bilan HR gaplashishi kerak, shuning uchun ular
 * ajratib ko'rsatiladi va ro'yxat tepasida turadi.
 *
 * ⚠️ FAQAT ENG SO'NGGI VERSIYA. Yo'riqnoma yangilansa ro'yxat
 * qaytadan ochiladi — eski tanishuv o'tmaydi (xodim eski matnga
 * rozi bo'lgan).
 */
function TanishuvPaneli() {
  const { data, isLoading } = useInstructionAcks();
  const [ochiq, setOchiq] = useState<number | null>(null);

  if (isLoading) return <Skeleton className="h-24 w-full" />;
  if (!data?.length)
    return (
      <p className="text-sm text-slate-600">
        Hali hech qaysi lavozimga yo'riqnoma kiritilmagan.
      </p>
    );

  return (
    <div className="space-y-2 text-sm">
      {data.map((b) => (
        <div key={b.object_id} className="rounded border">
          <button
            className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left"
            onClick={() => setOchiq(ochiq === b.object_id ? null : b.object_id)}
          >
            <span className="min-w-0">
              <span className="font-medium">{b.title ?? `Lavozim #${b.object_id}`}</span>
              <span className="text-xs text-slate-600"> · v{b.version}</span>
            </span>
            <span className="flex shrink-0 items-center gap-2 text-xs">
              <span className={b.pending.length ? "text-amber-700" : "text-emerald-700"}>
                {b.read.length}/{b.total} tanishgan
              </span>
              {b.exhausted_count > 0 && (
                <span className="flex items-center gap-1 rounded bg-red-100 px-1.5 py-0.5 text-red-800">
                  <BellOff className="h-3 w-3" />
                  {b.exhausted_count}
                </span>
              )}
            </span>
          </button>
          {ochiq === b.object_id && (
            <div className="space-y-2 border-t px-3 py-2">
              {!!b.pending.length && (
                <div>
                  <div className="mb-1 text-xs text-slate-600">
                    Tanishmaganlar ({b.pending.length}):
                  </div>
                  <ul className="space-y-0.5">
                    {b.pending.map((u) => (
                      <li key={u.user_id} className="flex items-center gap-1.5">
                        {u.exhausted && <BellOff className="h-3.5 w-3.5 text-red-600" />}
                        <span>{u.full_name}</span>
                        <span className="text-xs text-slate-600">
                          · {u.reminder_count} eslatma
                          {u.exhausted ? " · bot jim, HR gaplashsin" : ""}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {!!b.read.length && (
                <div>
                  <div className="mb-1 text-xs text-slate-600">
                    Tanishganlar ({b.read.length}):
                  </div>
                  <ul className="space-y-0.5 text-slate-700">
                    {b.read.map((u) => (
                      <li key={u.user_id}>
                        {u.full_name}
                        {u.acknowledged_at
                          ? ` · ${u.acknowledged_at.slice(0, 10)}`
                          : ""}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

export default function OrgChart() {
  const { data: chart, isLoading } = useOrgChart();
  const [openId, setOpenId] = useState<number | null>(null);
  const { data: detail } = useOrgPosition(openId);
  const { data: versions } = useOrgDescriptions(openId);
  const { data: profile } = useOrgProfile();

  const setParent = useOrgSetParent();
  const addDesc = useOrgAddDescription();
  const saveProfile = useOrgSaveProfile();

  //  Yangi yo'riqnoma matni
  const [purpose, setPurpose] = useState("");
  const [duties, setDuties] = useState("");
  const [rights, setRights] = useState("");
  const [resp, setResp] = useState("");
  const [reqs, setReqs] = useState("");

  //  Kompaniya profili
  const [mission, setMission] = useState("");
  const [values, setValues] = useState("");
  const [goals, setGoals] = useState("");
  const [profOpen, setProfOpen] = useState(false);

  const bolalar = useMemo(() => {
    const m = new Map<number | null, OrgNode[]>();
    for (const n of chart?.nodes ?? []) {
      const k = n.parent_id;
      m.set(k, [...(m.get(k) ?? []), n]);
    }
    return m;
  }, [chart]);

  const ildizlar = bolalar.get(null) ?? [];

  function qatorlar(s: string): string[] {
    return s.split("\n").map((x) => x.trim()).filter(Boolean);
  }

  async function yoriqnomaQosh() {
    if (openId === null) return;
    const res = await addDesc.mutateAsync({
      id: openId,
      body: {
        purpose: purpose.trim() || null,
        duties: qatorlar(duties),
        rights: qatorlar(rights),
        responsibility: qatorlar(resp),
        requirements: qatorlar(reqs),
      },
    });
    setPurpose("");
    setDuties("");
    setRights("");
    setResp("");
    setReqs("");
    toast.success(
      `${res.version}-versiya yaratildi. Eski versiya o'z holicha qoldi.`
    );
  }

  const yoriqnomasizlar = chart?.gaps?.without_description ?? [];
  const rahbarsizlar = chart?.gaps?.without_manager ?? [];

  return (
    <div className="space-y-4">
      <PageHeader title="Tashkiliy tuzilma" />

      {/* ── Yo'riqnoma tanishuvi (S-42) ── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Yo'riqnoma bilan tanishuv</CardTitle>
        </CardHeader>
        <CardContent>
          <TanishuvPaneli />
        </CardContent>
      </Card>

      {/* ── Bo'shliqlar ──
          ⚠️ `gaps` bo'sh KELISHI MUMKIN: server uni faqat rahbarga
          yuboradi (S-41). Bu sahifa rahbar uchun, lekin maydonlar
          ATAYLAB majburiy emas — kim ko'rayotganini backend hal
          qiladi, mijoz esa yo'qligiga chidashi kerak. */}
      {!!(yoriqnomasizlar.length || rahbarsizlar.length) && (
        <Card className="border-amber-300 bg-amber-50/60">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <AlertTriangle className="h-4 w-4 text-amber-600" />
              Bo'shliqlar
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {!!yoriqnomasizlar.length && (
              <div>
                <div className="mb-1 text-xs text-slate-600">
                  Yo'riqnomasi yo'q lavozimlar ({yoriqnomasizlar.length}):
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {yoriqnomasizlar.map((g) => (
                    <button
                      key={g.id}
                      className="rounded bg-white px-2 py-0.5 text-xs underline"
                      onClick={() => setOpenId(g.id)}
                    >
                      {g.name}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {!!rahbarsizlar.length && (
              <div>
                <div className="mb-1 flex items-center gap-1 text-xs text-slate-600">
                  <UserX className="h-3.5 w-3.5" />
                  Rahbari belgilanmagan xodimlar ({rahbarsizlar.length}):
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {rahbarsizlar.map((u) => (
                    <span key={u.id} className="rounded bg-white px-2 py-0.5 text-xs">
                      {u.full_name}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* ── Sxema ── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Network className="h-4 w-4" />
            Lavozimlar sxemasi
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <Skeleton className="h-32 w-full" />
          ) : !chart?.nodes.length ? (
            <div className="rounded-lg border border-dashed p-4 text-sm text-slate-600">
              Lavozimlar yo'q.
            </div>
          ) : (
            <>
              <ul>
                {ildizlar.map((n) => (
                  <Tugun
                    key={n.id}
                    node={n}
                    bolalar={bolalar}
                    onSelect={setOpenId}
                    tanlangan={openId}
                    daraja={0}
                  />
                ))}
              </ul>
              {/*  Ota-lavozimi belgilanmagan, lekin ildiz ham
                  bo'lmasligi kerak bo'lganlar — HR ularni ko'rsin. */}
              {ildizlar.length === chart.nodes.length && chart.nodes.length > 1 && (
                <p className="mt-2 text-xs text-slate-500">
                  Hech bir lavozimga ota belgilanmagan — sxema tekis ro'yxat
                  ko'rinishida. Lavozimni tanlab «Ota lavozim» ni qo'ying.
                </p>
              )}
            </>
          )}
        </CardContent>
      </Card>

      {/* ── Tanlangan lavozim ── */}
      {openId !== null && detail && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">{detail.name}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            <div className="flex flex-wrap items-end gap-2">
              <div className="w-64">
                <div className="mb-1 text-xs text-slate-600">Ota lavozim</div>
                <Select
                  value={detail.parent ? String(detail.parent.id) : YOQ}
                  onValueChange={async (v) => {
                    await setParent.mutateAsync({
                      id: openId,
                      parentId: v === YOQ ? null : Number(v),
                    });
                    toast.success("Bo'ysunish yangilandi");
                  }}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={YOQ}>— yo'q (eng yuqori) —</SelectItem>
                    {(chart?.nodes ?? [])
                      .filter((n) => n.id !== openId)
                      .map((n) => (
                        <SelectItem key={n.id} value={String(n.id)}>
                          {n.name}
                        </SelectItem>
                      ))}
                  </SelectContent>
                </Select>
              </div>
              <span className="pb-2 text-xs text-slate-600">
                {detail.employees.length} xodim / {detail.units} o'rin
                {detail.vacant > 0 && ` · ${detail.vacant} bo'sh`}
                {detail.vacant < 0 && ` · shtatdan ${-detail.vacant} ortiq`}
              </span>
            </div>

            <div>
              <div className="mb-1 text-xs text-slate-600">Bu lavozimda ishlaydiganlar</div>
              {detail.employees.length ? (
                <div className="flex flex-wrap gap-1.5">
                  {detail.employees.map((u) => (
                    <span key={u.id} className="rounded bg-slate-100 px-2 py-0.5 text-xs">
                      {u.full_name}
                    </span>
                  ))}
                </div>
              ) : (
                <span className="text-xs text-slate-500">Hech kim ishlamayapti.</span>
              )}
            </div>

            {/* ── Joriy yo'riqnoma ── */}
            <div className="rounded border p-3">
              <div className="mb-2 flex items-center gap-2">
                <span className="font-medium">Yo'riqnoma</span>
                {detail.description ? (
                  <span className="text-xs text-slate-600">
                    {detail.description.version}-versiya ·{" "}
                    {detail.description.effective_from} dan
                  </span>
                ) : (
                  <span className="text-xs text-amber-700">hali yo'q</span>
                )}
              </div>
              {detail.description && (
                <div className="space-y-1.5 text-xs">
                  {detail.description.purpose && (
                    <p>
                      <b>Maqsad:</b> {detail.description.purpose}
                    </p>
                  )}
                  {(
                    [
                      ["Vazifalar", detail.description.duties],
                      ["Huquqlar", detail.description.rights],
                      ["Javobgarlik", detail.description.responsibility],
                      ["Talablar", detail.description.requirements],
                    ] as const
                  ).map(([nom, ro]) =>
                    ro.length ? (
                      <div key={nom}>
                        <b>{nom}:</b>
                        <ul className="ml-4 list-disc">
                          {ro.map((x, i) => (
                            <li key={i}>{x}</li>
                          ))}
                        </ul>
                      </div>
                    ) : null
                  )}
                </div>
              )}
              {!!versions?.length && (
                <p className="mt-2 text-xs text-slate-500">
                  Jami {versions.length} ta versiya — eskilari saqlanadi.
                </p>
              )}
            </div>

            {/* ── YANGI versiya ──
                ⚠️ Tahrirlash EMAS: yo'riqnoma huquqiy hujjat, xodim
                «tanishdim» degan matn o'zgarmasligi kerak. */}
            <div className="rounded border border-dashed p-3">
              <div className="mb-2 flex items-center gap-1 text-sm font-medium">
                <Plus className="h-4 w-4" />
                Yangi versiya
              </div>
              <p className="mb-2 text-xs text-slate-600">
                Yo'riqnoma tahrirlanmaydi — har o'zgarish yangi versiya bo'lib
                qo'shiladi, eskisi o'z holicha qoladi.
              </p>
              <div className="space-y-2">
                <Input
                  placeholder="Lavozim maqsadi"
                  value={purpose}
                  onChange={(e) => setPurpose(e.target.value)}
                />
                {(
                  [
                    ["Vazifalar (har qatorda bittadan)", duties, setDuties],
                    ["Huquqlar", rights, setRights],
                    ["Javobgarlik", resp, setResp],
                    ["Talablar", reqs, setReqs],
                  ] as const
                ).map(([ph, val, set]) => (
                  <Textarea
                    key={ph}
                    rows={2}
                    placeholder={ph}
                    value={val}
                    onChange={(e) => (set as (v: string) => void)(e.target.value)}
                  />
                ))}
                <Button onClick={yoriqnomaQosh} disabled={addDesc.isPending}>
                  Versiya qo'shish
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ── Kompaniya profili ── */}
      <Card>
        <CardHeader className="flex-row items-center justify-between gap-2 pb-3">
          <CardTitle className="text-base">Kompaniya haqida</CardTitle>
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              setMission(profile?.mission ?? "");
              setValues((profile?.values ?? []).join("\n"));
              setGoals((profile?.goals ?? []).join("\n"));
              setProfOpen((v) => !v);
            }}
          >
            {profOpen ? "Yopish" : "Tahrirlash"}
          </Button>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          {!profOpen ? (
            <>
              <p>
                <b>Missiya:</b> {profile?.mission || "—"}
              </p>
              <p>
                <b>Qadriyatlar:</b>{" "}
                {profile?.values.length ? profile.values.join(" · ") : "—"}
              </p>
              <p>
                <b>Strategik maqsadlar:</b>{" "}
                {profile?.goals.length ? profile.goals.join(" · ") : "—"}
              </p>
            </>
          ) : (
            <div className="space-y-2">
              <Textarea
                rows={2}
                placeholder="Missiya"
                value={mission}
                onChange={(e) => setMission(e.target.value)}
              />
              <Textarea
                rows={2}
                placeholder="Qadriyatlar (har qatorda bittadan)"
                value={values}
                onChange={(e) => setValues(e.target.value)}
              />
              <Textarea
                rows={2}
                placeholder="Strategik maqsadlar (har qatorda bittadan)"
                value={goals}
                onChange={(e) => setGoals(e.target.value)}
              />
              <Button
                onClick={async () => {
                  await saveProfile.mutateAsync({
                    mission: mission.trim() || null,
                    values: qatorlar(values),
                    goals: qatorlar(goals),
                  });
                  setProfOpen(false);
                  toast.success("Saqlandi");
                }}
                disabled={saveProfile.isPending}
              >
                Saqlash
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
