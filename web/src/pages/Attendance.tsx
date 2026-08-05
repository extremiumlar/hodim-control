/**
 * Davomat — rahbar sahifasi (UX-B: 8 bo'limli bitta skroll o'rniga 4 tab).
 *
 * Tab tanlov URL bilan sinxron (`?tab=`): sahifa yangilansa tab saqlanadi,
 * havola ulashilsa aynan o'sha tab ochiladi. Har tab o'z so'rovlarini FAQAT
 * ochiq bo'lganda yuboradi (`active` prop / `enabled`) — ilgari sahifa
 * ochilishi bilan 8 ta bo'limning hammasi yuklanardi.
 *
 * Tab mazmunlari `components/attendance/` ichida — 824-qatorlik yagona fayl
 * o'rniga har biri o'z faylida.
 */
import { useSearchParams } from "react-router-dom";
import PageHeader from "@/components/PageHeader";
import MatrixTab from "@/components/attendance/MatrixTab";
import ReportTab from "@/components/attendance/ReportTab";
import SettingsTab from "@/components/attendance/SettingsTab";
import TodayTab from "@/components/attendance/TodayTab";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAuth } from "@/lib/auth";
import { useFaceReregList } from "@/lib/queries";

const TAB_KEYS = ["bugun", "jadval", "hisobot", "sozlamalar"] as const;
type TabKey = (typeof TAB_KEYS)[number];

export default function Attendance() {
  const { user } = useAuth();
  const isDasturchi = user?.role === "dasturchi";
  // Qo'lda tuzatish — HR/Boshliq/Dasturchi ROLI bo'yicha, YOKI Dasturchi
  // shaxsan bergan `can_edit_attendance` bayrog'i bilan (ROP yoki oddiy
  // xodim ham bo'lishi mumkin). Backend aynan shu qoidani tekshiradi.
  const canEdit =
    !!user && (["hr", "boss", "dasturchi"].includes(user.role) || user.can_edit_attendance);
  // Joylashuv ruxsatini berish — ATAYLAB bayroqsiz, faqat ROL bo'yicha:
  // `can_edit_attendance` egasi o'tmish yozuvini tuzatadi, GPS'ni butunlay
  // chetlab o'tish huquqini TARQATA olmasligi kerak (backend ham shunday).
  const canManageLocationExempt = !!user && ["hr", "boss", "dasturchi"].includes(user.role);
  // Sozlamalar tabi (yuz so'rovlari + joylashuv ruxsati) — faqat shu rollar;
  // `can_edit_attendance` bayrog'i egasiga bu tab ko'rinmaydi.
  const canSeeSettings = canManageLocationExempt;

  const [searchParams, setSearchParams] = useSearchParams();
  const rawTab = searchParams.get("tab");
  const tab: TabKey = TAB_KEYS.includes(rawTab as TabKey) ? (rawTab as TabKey) : "bugun";

  // Sozlamalar tabidagi kutilayotgan yuz so'rovlari soni — tab yorlig'ida
  // badge (HR botdagi xabarni o'tkazib yuborgan bo'lsa ham sezsin).
  const pendingRereg = useFaceReregList("pending", canSeeSettings);
  const reregCount = pendingRereg.data?.length ?? 0;

  return (
    <div className="space-y-4">
      <PageHeader title="Davomat (kelib-ketish)" />

      <Tabs
        value={tab}
        onValueChange={(v) => {
          // replace emas — orqaga tugmasi tablar orasida ishlashi tabiiy
          setSearchParams({ tab: v });
        }}
      >
        <TabsList>
          <TabsTrigger value="bugun">Bugun</TabsTrigger>
          <TabsTrigger value="jadval">Oylik jadval</TabsTrigger>
          <TabsTrigger value="hisobot">Hisobot</TabsTrigger>
          {canSeeSettings && (
            <TabsTrigger value="sozlamalar">
              Sozlamalar
              {reregCount > 0 && (
                <span className="ml-1.5 rounded-full bg-amber-100 px-1.5 py-0.5 text-[11px] font-bold text-amber-700">
                  {reregCount}
                </span>
              )}
            </TabsTrigger>
          )}
        </TabsList>

        <TabsContent value="bugun" className="mt-4">
          <TodayTab active={tab === "bugun"} />
        </TabsContent>
        <TabsContent value="jadval" className="mt-4">
          <MatrixTab active={tab === "jadval"} canEdit={canEdit} isDasturchi={isDasturchi} />
        </TabsContent>
        <TabsContent value="hisobot" className="mt-4">
          <ReportTab active={tab === "hisobot"} />
        </TabsContent>
        {canSeeSettings && (
          <TabsContent value="sozlamalar" className="mt-4">
            <SettingsTab
              active={tab === "sozlamalar"}
              canManageLocationExempt={canManageLocationExempt}
            />
          </TabsContent>
        )}
      </Tabs>
    </div>
  );
}
