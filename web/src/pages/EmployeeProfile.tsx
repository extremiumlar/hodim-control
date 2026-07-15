import { FormEvent, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { format } from "date-fns";
import { ArrowLeft, ChevronDown, ChevronUp } from "lucide-react";
import { toast } from "sonner";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { type ColumnDef } from "@tanstack/react-table";
import DataTable from "@/components/DataTable";
import PageHeader from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { type DailyResult } from "@/lib/api";
import {
  useBonuses,
  useCreateManualDailyResult,
  useDailyResults,
  useSetManualMobilografVideos,
  useUser,
} from "@/lib/queries";

const SOURCE_LABELS: Record<string, string> = { crm: "CRM", manual: "Qo'lda" };

const resultColumns: ColumnDef<DailyResult>[] = [
  {
    accessorKey: "date",
    header: "Sana",
    cell: ({ row }) => format(new Date(row.original.date), "dd.MM.yyyy"),
  },
  { accessorKey: "conversations_count", header: "Suhbatlar" },
  { accessorKey: "visits_count", header: "Tashriflar" },
  {
    accessorKey: "source",
    header: "Manba",
    cell: ({ row }) => SOURCE_LABELS[row.original.source] ?? row.original.source,
  },
];

export default function EmployeeProfile() {
  const { id } = useParams<{ id: string }>();
  const userId = Number(id);

  const userQuery = useUser(userId);
  const resultsQuery = useDailyResults(userId);
  const bonusesQuery = useBonuses(userId);
  const saveDaily = useCreateManualDailyResult();
  const saveVideos = useSetManualMobilografVideos();

  const [expandedBonus, setExpandedBonus] = useState<number | null>(null);
  const [date, setDate] = useState(format(new Date(), "yyyy-MM-dd"));
  const [conversations, setConversations] = useState("");
  const [visits, setVisits] = useState("");
  const [videos, setVideos] = useState("");

  const employee = userQuery.data;

  // Lavozimda kuzatiladigan ko'rsatkichlar — forma faqat shu maydonlarni ko'rsatadi
  // (lavozim yo'q bo'lsa standart suhbat+tashrif, backend metrics_for bilan bir xil).
  const trackedMetrics =
    employee?.position?.metrics && employee.position.metrics.length > 0
      ? employee.position.metrics
      : ["suhbat", "tashrif"];
  const tracksSuhbat = trackedMetrics.includes("suhbat");
  const tracksTashrif = trackedMetrics.includes("tashrif");
  const tracksVideo = trackedMetrics.includes("video");

  const submitting = saveDaily.isPending || saveVideos.isPending;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();

    // Ko'rinmaydigan (lavozimda kuzatilmaydigan) maydonlar 0 sifatida yuboriladi
    const conversationsCount = tracksSuhbat ? Number(conversations) : 0;
    const visitsCount = tracksTashrif ? Number(visits) : 0;
    const videosCount = tracksVideo ? Number(videos) : 0;
    if ([conversationsCount, visitsCount, videosCount].some((v) => !Number.isInteger(v) || v < 0)) {
      toast.error("Ko'rsatkichlar soni manfiy bo'lmagan butun son bo'lishi kerak");
      return;
    }

    try {
      if (tracksSuhbat || tracksTashrif) {
        await saveDaily.mutateAsync({
          user_id: userId,
          date,
          conversations_count: conversationsCount,
          visits_count: visitsCount,
        });
      }
      if (tracksVideo) {
        await saveVideos.mutateAsync({ user_id: userId, date, confirmed_count: videosCount });
      }
      setConversations("");
      setVisits("");
      setVideos("");
      toast.success("Kunlik natija saqlandi");
    } catch {
      // xato toast'i useApiMutation ichida ko'rsatiladi
    }
  };

  if (userQuery.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-9 w-64" />
        <div className="grid gap-6 md:grid-cols-3">
          <Skeleton className="h-72 rounded-xl" />
          <Skeleton className="h-72 rounded-xl md:col-span-2" />
        </div>
      </div>
    );
  }

  const results = resultsQuery.data ?? [];
  const bonuses = bonusesQuery.data ?? [];

  const chartData = [...results]
    .sort((a, b) => a.date.localeCompare(b.date))
    .map((r) => ({ date: r.date.slice(5), suhbat: r.conversations_count, tashrif: r.visits_count }));

  return (
    <div className="space-y-6">
      <div>
        <Link to="/norms" className="inline-flex items-center gap-1 text-sm text-primary hover:underline">
          <ArrowLeft className="h-3.5 w-3.5" />
          Orqaga
        </Link>
        <PageHeader title={employee?.full_name ?? ""} description="Xodim profili" />
      </div>

      <div className="grid gap-6 md:grid-cols-3">
        <Card className="h-fit md:col-span-1">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Kunlik natijani qo'lda kiritish</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="mb-3 text-xs text-slate-400">
              CRM ulanmagan bo'lsa yoki tuzatish kerak bo'lsa shu yerdan kiriting.
            </p>
            <form onSubmit={handleSubmit} className="space-y-3">
              <div>
                <Label htmlFor="ep-date">Sana</Label>
                <Input
                  id="ep-date"
                  type="date"
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                  required
                />
              </div>
              {tracksSuhbat && (
                <div>
                  <Label htmlFor="ep-conv">Suhbatlar soni</Label>
                  <Input
                    id="ep-conv"
                    type="number"
                    value={conversations}
                    onChange={(e) => setConversations(e.target.value)}
                    required
                  />
                </div>
              )}
              {tracksTashrif && (
                <div>
                  <Label htmlFor="ep-visits">Tashriflar soni</Label>
                  <Input
                    id="ep-visits"
                    type="number"
                    value={visits}
                    onChange={(e) => setVisits(e.target.value)}
                    required
                  />
                </div>
              )}
              {tracksVideo && (
                <div>
                  <Label htmlFor="ep-videos">Tasdiqlangan videolar soni</Label>
                  <Input
                    id="ep-videos"
                    type="number"
                    value={videos}
                    onChange={(e) => setVideos(e.target.value)}
                    required
                  />
                  <p className="mt-1 text-xs text-slate-400">
                    Guruh reaksiyasi ishlamay qolganda shu yerdan kiriting — kun uchun qo'lda
                    kiritilgan son qayta kiritilsa ustidan yoziladi.
                  </p>
                </div>
              )}
              <Button type="submit" disabled={submitting} className="w-full">
                {submitting ? "Saqlanmoqda..." : "Saqlash"}
              </Button>
            </form>
          </CardContent>
        </Card>

        <div className="space-y-6 md:col-span-2">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Tendensiya</CardTitle>
            </CardHeader>
            <CardContent>
              {chartData.length === 0 ? (
                <p className="text-sm text-slate-500">Grafik uchun hali ma'lumot yo'q.</p>
              ) : (
                <ResponsiveContainer width="100%" height={260}>
                  <LineChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="date" fontSize={12} />
                    <YAxis fontSize={12} />
                    <Tooltip />
                    <Legend />
                    <Line
                      type="monotone"
                      dataKey="suhbat"
                      name="Suhbatlar"
                      stroke="#4f46e5"
                      strokeWidth={2}
                      dot={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="tashrif"
                      name="Tashriflar"
                      stroke="#10b981"
                      strokeWidth={2}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>

          <div>
            <h3 className="mb-2 font-semibold">Kunlik natijalar tarixi</h3>
            <DataTable
              columns={resultColumns}
              data={resultsQuery.data}
              isLoading={resultsQuery.isLoading}
              error={resultsQuery.error ? resultsQuery.error.message : null}
              onRetry={() => resultsQuery.refetch()}
              empty={{ text: "Hozircha ma'lumot yo'q." }}
            />
          </div>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Bonus tarixi</CardTitle>
            </CardHeader>
            <CardContent>
              {bonuses.length === 0 ? (
                <p className="text-sm text-slate-500">Hali bonus hisoblanmagan.</p>
              ) : (
                <div className="space-y-2">
                  {bonuses.map((b) => (
                    <div key={b.id} className="rounded border">
                      <button
                        onClick={() => setExpandedBonus(expandedBonus === b.id ? null : b.id)}
                        className="flex w-full items-center justify-between px-3 py-2 text-sm hover:bg-slate-50"
                      >
                        <span>
                          {b.period} —{" "}
                          <span className="font-medium">{b.amount.toLocaleString()} so'm</span>
                        </span>
                        <span className="flex items-center gap-1 text-xs text-slate-400">
                          {expandedBonus === b.id ? (
                            <>
                              yopish <ChevronUp className="h-3.5 w-3.5" />
                            </>
                          ) : (
                            <>
                              tafsilot <ChevronDown className="h-3.5 w-3.5" />
                            </>
                          )}
                        </span>
                      </button>
                      {expandedBonus === b.id && b.breakdown && (
                        <div className="space-y-1 px-3 pb-3 text-xs text-slate-600">
                          {Object.entries(b.breakdown).map(([key, value]) => (
                            <div key={key} className="flex justify-between border-b border-dashed py-1">
                              <span className="text-slate-400">{key}</span>
                              <span>{String(value)}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
