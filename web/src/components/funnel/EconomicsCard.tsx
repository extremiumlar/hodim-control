/**
 * Reklama xarajati va birlik iqtisodiyoti (voronka 3-bosqich).
 *
 * Tizimning YAGONA qo'lda kiritiladigan qismi: xarajat na tizimda, na CRM'da
 * bor. Oyiga bir marta to'ldiriladi.
 *
 * KANAL NOMI RO'YXATDAN TANLANADI — qo'lda yozilsa («telegram» vs
 * «#telegram») xarajat lidlar bilan bog'lanmay qolardi va CPL jimgina
 * noto'g'ri chiqardi.
 */
import { useState, type FormEvent } from "react";
import { Trash2, Wallet } from "lucide-react";
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
import { Skeleton } from "@/components/ui/skeleton";
import { fmtMoney } from "@/lib/utils";
import {
  useDeleteAdSpend,
  useFunnelEconomics,
  useFunnelKnownChannels,
  useSetAdSpend,
  useSetAvgDealProfit,
} from "@/lib/queries";

const num = (v: number | null | undefined, suffix = "") =>
  v === null || v === undefined ? "—" : `${fmtMoney(v)}${suffix}`;

export default function EconomicsCard({
  period,
  groupBy,
  canEdit,
}: {
  period: string;
  groupBy: "tag" | "source";
  canEdit: boolean;
}) {
  const eco = useFunnelEconomics(period, groupBy);
  const known = useFunnelKnownChannels(period, groupBy);
  const setSpend = useSetAdSpend(period, groupBy);
  const delSpend = useDeleteAdSpend(period, groupBy);
  const setProfit = useSetAvgDealProfit(period, groupBy);

  const [channel, setChannel] = useState("");
  const [amount, setAmount] = useState("");
  const [reach, setReach] = useState("");
  const [profit, setProfit2] = useState("");

  const d = eco.data;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!channel) {
      toast.error("Kanalni tanlang");
      return;
    }
    const n = Number(amount);
    if (!n || n <= 0) {
      toast.error("Summa musbat son bo'lishi kerak");
      return;
    }
    setSpend.mutate(
      { period, channel, amount: n, reach: reach ? Number(reach) : null },
      {
        onSuccess: () => {
          toast.success("Xarajat saqlandi");
          setAmount("");
          setReach("");
        },
      }
    );
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Wallet className="size-4" /> Reklama xarajati va birlik iqtisodiyoti
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {eco.isLoading && !d ? (
          <Skeleton className="h-40 w-full" />
        ) : (
          <>
            {d && d.rows.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-xs uppercase text-muted-foreground">
                      <th className="py-2 text-left font-medium">Kanal</th>
                      <th className="py-2 text-right font-medium">Xarajat</th>
                      <th className="py-2 text-right font-medium">Lid</th>
                      <th className="py-2 text-right font-medium">Shartnoma</th>
                      <th className="py-2 text-right font-medium">CPL</th>
                      <th className="py-2 text-right font-medium">CAC</th>
                      <th className="py-2 text-right font-medium">ROMI</th>
                      {canEdit && <th className="py-2" />}
                    </tr>
                  </thead>
                  <tbody>
                    {d.rows.map((r) => (
                      <tr key={r.id} className="border-b last:border-0">
                        <td className="py-1.5">
                          {r.channel}
                          {!r.matched && (
                            <span
                              className="ml-2 rounded bg-destructive/10 px-1.5 py-0.5 text-xs text-destructive"
                              title="Bu nom voronkadagi hech bir kanalga mos kelmadi — xarajat lidlarga bog'lanmadi"
                            >
                              mos kelmadi
                            </span>
                          )}
                        </td>
                        <td className="py-1.5 text-right font-mono">{fmtMoney(r.amount)}</td>
                        <td className="py-1.5 text-right font-mono">{r.leads}</td>
                        <td className="py-1.5 text-right font-mono font-semibold">
                          {r.contracts}
                        </td>
                        <td className="py-1.5 text-right font-mono">{num(r.cpl)}</td>
                        <td className="py-1.5 text-right font-mono">{num(r.cac)}</td>
                        <td
                          className={`py-1.5 text-right font-mono ${
                            r.romi !== null && r.romi < 0 ? "text-destructive" : ""
                          }`}
                        >
                          {r.romi === null ? "—" : `${r.romi}%`}
                        </td>
                        {canEdit && (
                          <td className="py-1.5 text-right">
                            <Button
                              variant="ghost"
                              size="sm"
                              aria-label="O'chirish"
                              onClick={() => delSpend.mutate(r.id)}
                            >
                              <Trash2 className="size-4" />
                            </Button>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr className="border-t-2 font-semibold">
                      <td className="py-2">JAMI</td>
                      <td className="py-2 text-right font-mono">{fmtMoney(d.totals.spend)}</td>
                      <td className="py-2 text-right font-mono">{d.totals.leads}</td>
                      <td className="py-2 text-right font-mono">{d.totals.contracts}</td>
                      <td className="py-2 text-right font-mono">{num(d.totals.cpl)}</td>
                      <td className="py-2 text-right font-mono">{num(d.totals.cac)}</td>
                      <td className="py-2 text-right font-mono">
                        {d.totals.romi === null ? "—" : `${d.totals.romi}%`}
                      </td>
                      {canEdit && <td />}
                    </tr>
                  </tfoot>
                </table>
              </div>
            )}

            {d && d.rows.length === 0 && (
              <p className="rounded-md bg-muted p-3 text-sm">
                Bu oy uchun xarajat kiritilmagan — CPL va CAC hisoblanmaydi.
              </p>
            )}

            {d && d.missing_spend.length > 0 && (
              <p className="rounded-md bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-950/30">
                Lid keltirgan, lekin xarajati kiritilmagan kanallar:{" "}
                <b>{d.missing_spend.map((m) => m.channel).join(", ")}</b>
              </p>
            )}

            {d && d.avg_deal_profit === null && (
              <p className="text-xs text-muted-foreground">
                ROMI hisoblanishi uchun «bitta shartnomadan o'rtacha foyda» kiritilishi kerak —
                daromad CRM'da yo'q, tizim uni o'ylab topmaydi.
              </p>
            )}

            {canEdit && (
              <form onSubmit={submit} className="grid gap-3 border-t pt-4 sm:grid-cols-4">
                <div className="sm:col-span-2">
                  <Label>Kanal</Label>
                  <Select value={channel} onValueChange={setChannel}>
                    <SelectTrigger>
                      <SelectValue placeholder="Kanalni tanlang" />
                    </SelectTrigger>
                    <SelectContent>
                      {(known.data?.channels ?? []).map((c) => (
                        <SelectItem key={c.channel} value={c.channel}>
                          {c.channel} ({c.leads} lid)
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label htmlFor="sp-amount">Xarajat (so'm)</Label>
                  <Input
                    id="sp-amount"
                    type="number"
                    min={1}
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                  />
                </div>
                <div>
                  <Label htmlFor="sp-reach">Qamrov (ixtiyoriy)</Label>
                  <Input
                    id="sp-reach"
                    type="number"
                    min={0}
                    value={reach}
                    onChange={(e) => setReach(e.target.value)}
                  />
                </div>
                <div className="sm:col-span-4">
                  <Button type="submit" disabled={setSpend.isPending}>
                    {setSpend.isPending ? "Saqlanmoqda…" : "Xarajatni saqlash"}
                  </Button>
                </div>
              </form>
            )}

            {canEdit && (
              <div className="flex flex-wrap items-end gap-3 border-t pt-4">
                <div>
                  <Label htmlFor="sp-profit">Bitta shartnomadan o'rtacha foyda (so'm)</Label>
                  <Input
                    id="sp-profit"
                    type="number"
                    min={0}
                    className="w-56"
                    placeholder={d?.avg_deal_profit ? String(d.avg_deal_profit) : "kiritilmagan"}
                    value={profit}
                    onChange={(e) => setProfit2(e.target.value)}
                  />
                </div>
                <Button
                  variant="outline"
                  disabled={setProfit.isPending}
                  onClick={() =>
                    setProfit.mutate(
                      { period, value: profit ? Number(profit) : null },
                      { onSuccess: () => toast.success("Saqlandi — ROMI qayta hisoblandi") }
                    )
                  }
                >
                  Saqlash
                </Button>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
