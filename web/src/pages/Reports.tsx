import { FormEvent, useState } from "react";
import { format, startOfMonth } from "date-fns";
import { Download, FileSpreadsheet } from "lucide-react";
import { toast } from "sonner";
import PageHeader from "@/components/PageHeader";
import { DateRangePicker } from "@/components/PeriodPicker";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useDownloadReport } from "@/lib/queries";

export default function Reports() {
  const [dateFrom, setDateFrom] = useState(format(startOfMonth(new Date()), "yyyy-MM-dd"));
  const [dateTo, setDateTo] = useState(format(new Date(), "yyyy-MM-dd"));
  const download = useDownloadReport();

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    download.mutate(
      { dateFrom, dateTo },
      { onSuccess: () => toast.success("Excel fayl yuklab olindi") }
    );
  };

  return (
    <div>
      <PageHeader
        title="Hisobot eksporti (.xlsx)"
        description="Tanlangan davr bo'yicha har bir xodim uchun suhbatlar, tashriflar, vazifalar, sababli kunlar va (agar davr aniq bitta oyni qamrab olsa) bonus summasi Excel faylga eksport qilinadi."
      />
      <Card className="max-w-xl">
        <CardContent className="pt-6">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="mb-1 block text-sm text-slate-600">Davr</label>
              <DateRangePicker
                from={dateFrom}
                to={dateTo}
                onChange={(f, t) => {
                  setDateFrom(f);
                  setDateTo(t);
                }}
              />
            </div>
            <Button type="submit" disabled={download.isPending}>
              {download.isPending ? (
                <>
                  <FileSpreadsheet className="mr-2 h-4 w-4 animate-pulse" />
                  Tayyorlanmoqda...
                </>
              ) : (
                <>
                  <Download className="mr-2 h-4 w-4" />
                  Excel yuklab olish
                </>
              )}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
