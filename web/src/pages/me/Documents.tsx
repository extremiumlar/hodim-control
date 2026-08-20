/**
 * «Hujjatlarim» — xodim kabineti (TZ 3.4 / S-11).
 *
 * Xodim o'z kadr hujjatlarini ko'radi. Yuklab olish BOTDA: fayl
 * Telegram'da yotadi va uni qaytarish `send_file_id` orqali eng arzon
 * yo'l — serverga yuklab, keyin brauzerga uzatish disk va trafik
 * sarflaydi (kvota 1 GB).
 */
import PageHeader from "@/components/PageHeader";
import DocumentList from "@/components/documents/DocumentList";
import { useMyDocuments } from "@/lib/queries";

export default function MeDocuments() {
  const { data, isLoading } = useMyDocuments();

  return (
    <div className="space-y-4">
      <PageHeader title="Hujjatlarim" />
      <DocumentList
        documents={data}
        isLoading={isLoading}
        emptyText="Sizda hali hujjat yo'q. Mehnat shartnomasi, diplom va boshqalarni HR yuklaydi."
      />
    </div>
  );
}
