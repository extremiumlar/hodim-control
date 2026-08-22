/**
 * «O'quv paneli» — HR (TZ 3.1 / S-34).
 *
 * Zanjir: kurs yaratish → material qo'shish → savol qo'shish →
 * nashr qilish → tayinlash.
 *
 * ⚠️ Material FAYLI serverga yuklanmaydi — bot yuborgan Telegram
 * `file_id` biriktiriladi (kadr hujjatlari naqshi). Disk cheklangan,
 * video esa eng og'ir fayl turi.
 *
 * ⚠️ Savolsiz kursni nashr qilib bo'lmaydi — backend 400 beradi.
 * Aks holda xodim materialni ko'rib, «test yo'q» degan holatga
 * tushardi va kurs hech qachon yakunlanmasdi.
 */
import { useRef, useState } from "react";
import {
  BookOpen,
  CheckCircle2,
  FileUp,
  GraduationCap,
  ListChecks,
  Trash2,
  Users,
} from "lucide-react";
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
  useAddCourseMaterial,
  useAddCourseQuestion,
  useAssignCourse,
  useCourseAssignments,
  useCourseAudiences,
  useCourseDetail,
  useCourseMaterialKinds,
  useCourseReport,
  useCourses,
  useCreateCourse,
  useDeleteCourse,
  useDeleteCourseMaterial,
  useDeleteCourseQuestion,
  useImportCourseQuestions,
  usePositions,
  usePublishCourse,
  useUsers,
} from "@/lib/queries";

const ROLLAR = [
  { value: "employee", label: "Xodim" },
  { value: "rop", label: "ROP" },
  { value: "hr", label: "HR" },
  { value: "boss", label: "Boshliq" },
];

export default function Courses() {
  const { data: courses, isLoading } = useCourses();
  const { data: report } = useCourseReport();
  const { data: kinds } = useCourseMaterialKinds();
  const { data: audiences } = useCourseAudiences();
  const { data: users } = useUsers();
  const { data: positions } = usePositions();

  const create = useCreateCourse();
  const publish = usePublishCourse();
  const remove = useDeleteCourse();
  const addMaterial = useAddCourseMaterial();
  const delMaterial = useDeleteCourseMaterial();
  const addQuestion = useAddCourseQuestion();
  const delQuestion = useDeleteCourseQuestion();
  const importQ = useImportCourseQuestions();
  const assign = useAssignCourse();

  const [openId, setOpenId] = useState<number | null>(null);
  const { data: detail } = useCourseDetail(openId);
  const { data: assignments } = useCourseAssignments(openId);

  // ── Yangi kurs ──
  const [title, setTitle] = useState("");
  const [desc, setDesc] = useState("");
  const [pass, setPass] = useState("70");
  const [attempts, setAttempts] = useState("0");
  const [mandatory, setMandatory] = useState(false);

  // ── Yangi material ──
  const [mKind, setMKind] = useState("text");
  const [mTitle, setMTitle] = useState("");
  const [mBody, setMBody] = useState("");
  const [mFileId, setMFileId] = useState("");
  const [mUrl, setMUrl] = useState("");

  // ── Yangi savol ──
  const [qText, setQText] = useState("");
  const [qOpts, setQOpts] = useState("");
  const [qCorrect, setQCorrect] = useState("");
  const [qPoints, setQPoints] = useState("1");
  const fileRef = useRef<HTMLInputElement>(null);

  // ── Tayinlash ──
  const [aud, setAud] = useState("all");
  const [scope, setScope] = useState<string[]>([]);
  const [due, setDue] = useState("");

  async function kursYarat() {
    if (title.trim().length < 3) {
      toast.error("Kurs nomi kamida 3 belgi");
      return;
    }
    const c = await create.mutateAsync({
      title: title.trim(),
      description: desc.trim() || null,
      pass_percent: Number(pass) || 0,
      max_attempts: Number(attempts) || 0,
      is_mandatory: mandatory,
    });
    setTitle("");
    setDesc("");
    setOpenId(c.id);
    toast.success("Kurs yaratildi — endi material va savol qo'shing");
  }

  async function materialQosh() {
    if (openId === null) return;
    await addMaterial.mutateAsync({
      id: openId,
      body: {
        kind: mKind,
        title: mTitle.trim(),
        body: mBody.trim() || null,
        file_id: mFileId.trim() || null,
        url: mUrl.trim() || null,
      },
    });
    setMTitle("");
    setMBody("");
    setMFileId("");
    setMUrl("");
    toast.success("Material qo'shildi");
  }

  async function savolQosh() {
    if (openId === null) return;
    const variantlar = qOpts
      .split("\n")
      .map((x) => x.trim())
      .filter(Boolean);
    await addQuestion.mutateAsync({
      id: openId,
      body: {
        text: qText.trim(),
        options: variantlar,
        correct_index: variantlar.length ? Number(qCorrect) : null,
        points: Number(qPoints) || 1,
      },
    });
    setQText("");
    setQOpts("");
    setQCorrect("");
    toast.success("Savol qo'shildi");
  }

  async function savolYukla(f: File) {
    if (openId === null) return;
    const res = await importQ.mutateAsync({ id: openId, file: f });
    toast.success(
      `${res.added} ta savol yuklandi. Ular OCHIQ javobli — variant qo'shish uchun tahrirlang.`
    );
  }

  async function tayinla() {
    if (openId === null) return;
    const res = await assign.mutateAsync({
      id: openId,
      body: {
        audience: aud,
        scope_ids: aud === "all" ? null : scope,
        due_date: due || null,
      },
    });
    toast.success(
      `Qamrov: ${res.audience_size} · yangi tayinlash: ${res.created} · ` +
        `allaqachon bor edi: ${res.skipped}`
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader title="O'quv paneli" />

      {/* ── S-37: umumiy hisobot ──
          ⚠️ Raqamlar CRON'da hisoblanadi, bu sahifa faqat o'qiydi.
          Shuning uchun ular bir necha daqiqa eskirishi mumkin — sana
          ataylab ko'rsatiladi. */}
      {!!report?.assigned && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <ListChecks className="h-4 w-4" />
              Umumiy holat
              {report.computed_at && (
                <span className="text-xs font-normal text-slate-500">
                  · {new Date(report.computed_at).toLocaleString("ru-RU", {
                    day: "2-digit",
                    month: "2-digit",
                    hour: "2-digit",
                    minute: "2-digit",
                  })} holatiga
                </span>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2 text-xs">
            <span className="rounded bg-slate-100 px-2 py-1">
              Tayinlangan: <b>{report.assigned}</b>
            </span>
            <span className="rounded bg-slate-100 px-2 py-1">
              Boshlamagan: <b>{report.not_started}</b>
            </span>
            <span className="rounded bg-slate-100 px-2 py-1">
              Jarayonda: <b>{report.in_progress}</b>
            </span>
            <span className="rounded bg-emerald-100 px-2 py-1 text-emerald-900">
              O'tgan: <b>{report.passed}</b>
            </span>
            <span className="rounded bg-rose-100 px-2 py-1 text-rose-900">
              O'tmagan: <b>{report.failed}</b>
            </span>
            {report.pending_review > 0 && (
              <span className="rounded bg-amber-100 px-2 py-1 text-amber-900">
                Baholanmagan: <b>{report.pending_review}</b>
              </span>
            )}
            {report.overdue > 0 && (
              <span className="rounded bg-rose-100 px-2 py-1 text-rose-900">
                Muddati o'tgan: <b>{report.overdue}</b>
              </span>
            )}
            {report.mandatory_percent !== null && (
              <span className="rounded bg-slate-800 px-2 py-1 text-white">
                Majburiy kurs tugatish: <b>{report.mandatory_percent}%</b>
              </span>
            )}
          </CardContent>
        </Card>
      )}

      {/* ── Yangi kurs ── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <GraduationCap className="h-4 w-4" />
            Yangi kurs
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap items-end gap-2">
          <div className="min-w-[200px] flex-1">
            <div className="mb-1 text-xs text-slate-600">Nomi</div>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div className="min-w-[200px] flex-1">
            <div className="mb-1 text-xs text-slate-600">Tavsif</div>
            <Input value={desc} onChange={(e) => setDesc(e.target.value)} />
          </div>
          <div className="w-32">
            <div className="mb-1 text-xs text-slate-600">O'tish %</div>
            <Input
              value={pass}
              inputMode="numeric"
              onChange={(e) => setPass(e.target.value)}
            />
          </div>
          <div className="w-32">
            <div className="mb-1 text-xs text-slate-600">Urinish (0=∞)</div>
            <Input
              value={attempts}
              inputMode="numeric"
              onChange={(e) => setAttempts(e.target.value)}
            />
          </div>
          <label className="flex items-center gap-1.5 pb-2 text-sm">
            <input
              type="checkbox"
              checked={mandatory}
              onChange={(e) => setMandatory(e.target.checked)}
            />
            Majburiy
          </label>
          <Button onClick={kursYarat} disabled={create.isPending}>
            Yaratish
          </Button>
        </CardContent>
      </Card>

      {/* ── Kurslar ro'yxati ── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Kurslar</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <Skeleton className="h-24 w-full" />
          ) : !courses?.length ? (
            <div className="rounded-lg border border-dashed p-4 text-sm text-slate-600">
              Hali kurs yaratilmagan.
            </div>
          ) : (
            <ul className="divide-y">
              {courses.map((c) => (
                <li key={c.id} className="py-2.5 text-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      className="min-w-[160px] flex-1 text-left font-medium hover:underline"
                      onClick={() => setOpenId(openId === c.id ? null : c.id)}
                    >
                      {c.title}
                    </button>
                    {c.is_mandatory && (
                      <span className="rounded bg-rose-100 px-2 py-0.5 text-xs text-rose-900">
                        majburiy
                      </span>
                    )}
                    <span className="text-xs text-slate-600">
                      {c.material_count} material · {c.question_count} savol ·{" "}
                      {c.assigned_count} xodim · o'tish {c.pass_percent}%
                    </span>
                    {c.assigned_count > 0 && (
                      <span className="text-xs">
                        <span className="text-emerald-700">{c.passed} o'tdi</span>
                        {c.failed > 0 && (
                          <span className="text-rose-700"> · {c.failed} o'tmadi</span>
                        )}
                        {c.not_started > 0 && (
                          <span className="text-slate-600">
                            {" "}· {c.not_started} boshlamagan
                          </span>
                        )}
                        {c.overdue > 0 && (
                          <span className="text-rose-700">
                            {" "}· {c.overdue} muddati o'tgan
                          </span>
                        )}
                      </span>
                    )}
                    {c.is_published ? (
                      <span className="flex items-center gap-1 rounded bg-emerald-100 px-2 py-0.5 text-xs text-emerald-900">
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        nashrda
                      </span>
                    ) : (
                      <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-700">
                        qoralama
                      </span>
                    )}
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={async () => {
                        await publish.mutateAsync({
                          id: c.id,
                          value: !c.is_published,
                        });
                        toast.success(c.is_published ? "Yopildi" : "Nashr qilindi");
                      }}
                    >
                      {c.is_published ? "Yopish" : "Nashr qilish"}
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={async () => {
                        await remove.mutateAsync(c.id);
                        if (openId === c.id) setOpenId(null);
                        toast.success("O'chirildi (tarix saqlanadi)");
                      }}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {/* ── Tanlangan kurs ── */}
      {openId !== null && detail && (
        <>
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base">
                <BookOpen className="h-4 w-4" />
                Materiallar — {detail.course.title}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <ul className="divide-y">
                {detail.materials.map((m) => (
                  <li key={m.id} className="flex items-center gap-2 py-2 text-sm">
                    <span className="w-8 text-xs text-slate-500">{m.position}</span>
                    <span className="flex-1">
                      {m.title}
                      <span className="ml-2 text-xs text-slate-600">
                        {m.kind_label}
                        {m.file_id ? " · fayl biriktirilgan" : ""}
                      </span>
                    </span>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={async () => {
                        await delMaterial.mutateAsync({
                          id: openId,
                          materialId: m.id,
                        });
                        toast.success("Material o'chirildi");
                      }}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </li>
                ))}
                {!detail.materials.length && (
                  <li className="py-2 text-sm text-slate-600">Material yo'q.</li>
                )}
              </ul>

              <div className="flex flex-wrap items-end gap-2 border-t pt-3">
                <div className="w-40">
                  <div className="mb-1 text-xs text-slate-600">Turi</div>
                  <Select value={mKind} onValueChange={setMKind}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {(kinds ?? []).map((k) => (
                        <SelectItem key={k.value} value={k.value}>
                          {k.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="min-w-[160px] flex-1">
                  <div className="mb-1 text-xs text-slate-600">Nomi</div>
                  <Input value={mTitle} onChange={(e) => setMTitle(e.target.value)} />
                </div>
                {mKind === "text" && (
                  <div className="min-w-[200px] flex-1">
                    <div className="mb-1 text-xs text-slate-600">Matn</div>
                    <Input value={mBody} onChange={(e) => setMBody(e.target.value)} />
                  </div>
                )}
                {mKind === "link" && (
                  <div className="min-w-[200px] flex-1">
                    <div className="mb-1 text-xs text-slate-600">Havola</div>
                    <Input value={mUrl} onChange={(e) => setMUrl(e.target.value)} />
                  </div>
                )}
                {["video", "document", "photo"].includes(mKind) && (
                  <div className="min-w-[200px] flex-1">
                    <div className="mb-1 text-xs text-slate-600">
                      Telegram file_id (botga yuborib oling)
                    </div>
                    <Input
                      value={mFileId}
                      onChange={(e) => setMFileId(e.target.value)}
                      placeholder="BAACAgI..."
                    />
                  </div>
                )}
                <Button onClick={materialQosh} disabled={addMaterial.isPending}>
                  Qo'shish
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex-row items-center justify-between gap-2 pb-3">
              <CardTitle className="flex items-center gap-2 text-base">
                <ListChecks className="h-4 w-4" />
                Savollar
              </CardTitle>
              <div>
                <input
                  ref={fileRef}
                  type="file"
                  accept=".docx,.txt"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) savolYukla(f);
                    e.target.value = "";
                  }}
                />
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => fileRef.current?.click()}
                  disabled={importQ.isPending}
                >
                  <FileUp className="mr-1 h-4 w-4" />
                  .docx dan yuklash
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <ul className="divide-y">
                {detail.questions.map((q) => (
                  <li key={q.id} className="flex items-start gap-2 py-2 text-sm">
                    <span className="w-8 shrink-0 text-xs text-slate-500">
                      {q.position}
                    </span>
                    <span className="flex-1">
                      {q.text}
                      <span className="ml-2 text-xs text-slate-600">
                        {q.points} ball
                      </span>
                      {q.is_open ? (
                        <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-900">
                          ochiq — odam baholaydi
                        </span>
                      ) : (
                        <span className="ml-2 text-xs text-slate-600">
                          ({q.options.length} variant, to'g'ri: {q.options[q.correct_index ?? 0]})
                        </span>
                      )}
                    </span>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={async () => {
                        await delQuestion.mutateAsync({ id: openId, questionId: q.id });
                        toast.success("Savol o'chirildi");
                      }}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </li>
                ))}
                {!detail.questions.length && (
                  <li className="py-2 text-sm text-slate-600">
                    Savol yo'q — savolsiz kursni nashr qilib bo'lmaydi.
                  </li>
                )}
              </ul>

              <div className="flex flex-wrap items-end gap-2 border-t pt-3">
                <div className="min-w-[200px] flex-1">
                  <div className="mb-1 text-xs text-slate-600">Savol</div>
                  <Input value={qText} onChange={(e) => setQText(e.target.value)} />
                </div>
                <div className="min-w-[180px] flex-1">
                  <div className="mb-1 text-xs text-slate-600">
                    Variantlar (har qatorda bittadan; bo'sh = ochiq savol)
                  </div>
                  <Textarea
                    rows={2}
                    value={qOpts}
                    onChange={(e) => setQOpts(e.target.value)}
                  />
                </div>
                <div className="w-28">
                  <div className="mb-1 text-xs text-slate-600">To'g'ri (0 dan)</div>
                  <Input
                    value={qCorrect}
                    inputMode="numeric"
                    onChange={(e) => setQCorrect(e.target.value)}
                  />
                </div>
                <div className="w-24">
                  <div className="mb-1 text-xs text-slate-600">Ball</div>
                  <Input
                    value={qPoints}
                    inputMode="numeric"
                    onChange={(e) => setQPoints(e.target.value)}
                  />
                </div>
                <Button onClick={savolQosh} disabled={addQuestion.isPending}>
                  Qo'shish
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base">
                <Users className="h-4 w-4" />
                Tayinlash
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex flex-wrap items-end gap-2">
                <div className="w-48">
                  <div className="mb-1 text-xs text-slate-600">Kimga</div>
                  <Select
                    value={aud}
                    onValueChange={(v) => {
                      setAud(v);
                      setScope([]);
                    }}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {(audiences ?? []).map((a) => (
                        <SelectItem key={a.value} value={a.value}>
                          {a.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                {aud === "roles" && (
                  <div className="flex flex-wrap gap-2 pb-2">
                    {ROLLAR.map((r) => (
                      <label key={r.value} className="flex items-center gap-1 text-sm">
                        <input
                          type="checkbox"
                          checked={scope.includes(r.value)}
                          onChange={(e) =>
                            setScope((s) =>
                              e.target.checked
                                ? [...s, r.value]
                                : s.filter((x) => x !== r.value)
                            )
                          }
                        />
                        {r.label}
                      </label>
                    ))}
                  </div>
                )}
                {aud === "positions" && (
                  <div className="flex flex-wrap gap-2 pb-2">
                    {(positions ?? []).map((p) => (
                      <label key={p.id} className="flex items-center gap-1 text-sm">
                        <input
                          type="checkbox"
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
                  </div>
                )}
                {aud === "users" && (
                  <div className="max-h-32 min-w-[220px] flex-1 overflow-y-auto rounded border p-2">
                    {(users ?? []).map((u) => (
                      <label key={u.id} className="flex items-center gap-1 text-sm">
                        <input
                          type="checkbox"
                          checked={scope.includes(String(u.id))}
                          onChange={(e) =>
                            setScope((s) =>
                              e.target.checked
                                ? [...s, String(u.id)]
                                : s.filter((x) => x !== String(u.id))
                            )
                          }
                        />
                        {u.full_name}
                      </label>
                    ))}
                  </div>
                )}
                <div className="w-44">
                  <div className="mb-1 text-xs text-slate-600">Muddat</div>
                  <Input
                    type="date"
                    value={due}
                    onChange={(e) => setDue(e.target.value)}
                  />
                </div>
                <Button
                  onClick={tayinla}
                  disabled={assign.isPending || !detail.course.is_published}
                  title={
                    detail.course.is_published
                      ? undefined
                      : "Avval kursni nashr qiling"
                  }
                >
                  Tayinlash
                </Button>
              </div>

              <ul className="divide-y border-t">
                {(assignments ?? []).map((a) => (
                  <li key={a.id} className="flex flex-wrap items-center gap-2 py-2 text-sm">
                    <span className="min-w-[140px] flex-1">{a.user_name}</span>
                    <span className="text-xs text-slate-600">
                      {a.status} · urinish {a.attempt_no}
                      {a.due_date ? ` · muddat ${a.due_date}` : ""}
                    </span>
                    {a.percent !== null && (
                      <span
                        className={`rounded px-2 py-0.5 text-xs ${
                          a.pending_review
                            ? "bg-amber-100 text-amber-900"
                            : a.passed
                              ? "bg-emerald-100 text-emerald-900"
                              : "bg-rose-100 text-rose-900"
                        }`}
                      >
                        {a.percent}%{" "}
                        {a.pending_review
                          ? "· baholanmagan"
                          : a.passed
                            ? "· o'tdi"
                            : "· o'tmadi"}
                      </span>
                    )}
                  </li>
                ))}
                {!assignments?.length && (
                  <li className="py-2 text-sm text-slate-600">Hali tayinlanmagan.</li>
                )}
              </ul>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
