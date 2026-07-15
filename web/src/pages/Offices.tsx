import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { LocateFixed, MapPin, Pencil, Power, Trash2 } from "lucide-react";
import { toast } from "sonner";
import ConfirmDialog from "@/components/ConfirmDialog";
import PageHeader from "@/components/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { type Office } from "@/lib/api";
import { useCreateOffice, useDeleteOffice, useOffices, useUpdateOffice } from "@/lib/queries";

const officeSchema = z.object({
  name: z.string().trim().min(1, "Nomi to'ldirilishi shart"),
  latitude: z.coerce.number({ message: "Raqam kiriting" }).min(-90).max(90),
  longitude: z.coerce.number({ message: "Raqam kiriting" }).min(-180).max(180),
  radius_meters: z.coerce
    .number({ message: "Raqam kiriting" })
    .int("Butun son bo'lsin")
    .min(10, "Kamida 10 m")
    .max(10000, "Ko'pi bilan 10 km"),
});

// zod v4 + react-hook-form: kirish (string bo'lishi mumkin) va chiqish (coerce'dan
// keyin number) tiplari alohida.
type OfficeFormIn = z.input<typeof officeSchema>;
type OfficeFormOut = z.output<typeof officeSchema>;

export default function Offices() {
  const query = useOffices();
  const createOffice = useCreateOffice();
  const updateOffice = useUpdateOffice();
  const deleteOffice = useDeleteOffice();

  const [editingId, setEditingId] = useState<number | null>(null);
  const [deleting, setDeleting] = useState<Office | null>(null);
  const [locating, setLocating] = useState(false);

  const form = useForm<OfficeFormIn, unknown, OfficeFormOut>({
    resolver: zodResolver(officeSchema),
    defaultValues: { name: "", latitude: undefined, longitude: undefined, radius_meters: 150 },
  });

  const busy = createOffice.isPending || updateOffice.isPending;

  function myLocation() {
    if (!navigator.geolocation) {
      toast.error("Brauzer geolokatsiyani qo'llab-quvvatlamaydi.");
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        form.setValue("latitude", Number(pos.coords.latitude.toFixed(6)));
        form.setValue("longitude", Number(pos.coords.longitude.toFixed(6)));
        setLocating(false);
        toast.success("Joylashuv olindi — nom bering va saqlang.");
      },
      (e) => {
        setLocating(false);
        toast.error("GPS xato: " + e.message);
      },
      { enableHighAccuracy: true, timeout: 10000 }
    );
  }

  const onSubmit = form.handleSubmit((values) => {
    const data = { ...values, is_active: true };
    if (editingId != null) {
      updateOffice.mutate(
        { officeId: editingId, data: values },
        {
          onSuccess: () => {
            toast.success("Ofis yangilandi.");
            cancelEdit();
          },
        }
      );
    } else {
      createOffice.mutate(data, {
        onSuccess: () => {
          toast.success("Ofis qo'shildi.");
          form.reset();
        },
      });
    }
  });

  function startEdit(o: Office) {
    setEditingId(o.id);
    form.reset({
      name: o.name,
      latitude: o.latitude,
      longitude: o.longitude,
      radius_meters: o.radius_meters,
    });
  }

  function cancelEdit() {
    setEditingId(null);
    form.reset({ name: "", latitude: undefined, longitude: undefined, radius_meters: 150 });
  }

  const err = form.formState.errors;

  return (
    <div className="max-w-3xl space-y-6">
      <PageHeader
        title="Ofislar (davomat GPS)"
        description="Xodim «Keldim/Ketdim» qilganda joylashuvi shu ofislardan biriga (radius ichida) tushishi shart."
      />

      {/* Forma */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">
            {editingId != null ? "Ofisni tahrirlash" : "Yangi ofis"}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-3">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <div>
                <Label htmlFor="office-name">Nomi</Label>
                <Input id="office-name" placeholder="Masalan: Bosh ofis" {...form.register("name")} />
                {err.name && <p className="mt-1 text-xs text-rose-600">{err.name.message}</p>}
              </div>
              <div>
                <Label htmlFor="office-radius">Radius (metr)</Label>
                <Input id="office-radius" type="number" {...form.register("radius_meters")} />
                {err.radius_meters && (
                  <p className="mt-1 text-xs text-rose-600">{err.radius_meters.message}</p>
                )}
              </div>
              <div>
                <Label htmlFor="office-lat">Kenglik (latitude)</Label>
                <Input id="office-lat" placeholder="41.311081" {...form.register("latitude")} />
                {err.latitude && <p className="mt-1 text-xs text-rose-600">{err.latitude.message}</p>}
              </div>
              <div>
                <Label htmlFor="office-lng">Uzunlik (longitude)</Label>
                <Input id="office-lng" placeholder="69.240562" {...form.register("longitude")} />
                {err.longitude && (
                  <p className="mt-1 text-xs text-rose-600">{err.longitude.message}</p>
                )}
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="outline" onClick={myLocation} disabled={locating}>
                <LocateFixed className="mr-2 h-4 w-4" />
                {locating ? "Aniqlanmoqda..." : "Mening joyim"}
              </Button>
              <Button type="submit" disabled={busy}>
                {busy ? "Saqlanmoqda..." : editingId != null ? "Yangilash" : "Qo'shish"}
              </Button>
              {editingId != null && (
                <Button type="button" variant="ghost" onClick={cancelEdit}>
                  Bekor qilish
                </Button>
              )}
            </div>
          </form>
        </CardContent>
      </Card>

      {/* Ro'yxat */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Mavjud ofislar ({query.data?.length ?? 0})</CardTitle>
        </CardHeader>
        <CardContent>
          {query.isLoading ? (
            <div className="space-y-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : query.error ? (
            <div className="flex items-center justify-between rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
              {query.error.message}
              <Button variant="outline" size="sm" onClick={() => query.refetch()}>
                Qayta urinish
              </Button>
            </div>
          ) : query.data?.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-8 text-center">
              <MapPin className="h-8 w-8 text-slate-300" />
              <p className="text-sm text-amber-700">
                Hali ofis yo'q — xodimlar check-in qila olmaydi. Yuqoridan qo'shing.
              </p>
            </div>
          ) : (
            <ul className="divide-y divide-slate-100">
              {query.data?.map((o) => (
                <li key={o.id} className="flex items-center justify-between gap-3 py-3">
                  <div>
                    <div className="flex items-center gap-2 font-medium">
                      {o.name}
                      {!o.is_active && <Badge variant="secondary">faolsiz</Badge>}
                    </div>
                    <div className="text-xs text-slate-500">
                      {o.latitude}, {o.longitude} · radius {o.radius_meters} m
                    </div>
                  </div>
                  <div className="flex shrink-0 gap-1">
                    <Button variant="ghost" size="sm" onClick={() => startEdit(o)}>
                      <Pencil className="mr-1 h-3.5 w-3.5" />
                      Tahrirlash
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-amber-600 hover:text-amber-700"
                      onClick={() =>
                        updateOffice.mutate(
                          { officeId: o.id, data: { is_active: !o.is_active } },
                          {
                            onSuccess: () =>
                              toast.success(o.is_active ? "Ofis o'chirib qo'yildi." : "Ofis yoqildi."),
                          }
                        )
                      }
                    >
                      <Power className="mr-1 h-3.5 w-3.5" />
                      {o.is_active ? "O'chirib qo'yish" : "Yoqish"}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-rose-600 hover:text-rose-700"
                      onClick={() => setDeleting(o)}
                    >
                      <Trash2 className="mr-1 h-3.5 w-3.5" />
                      O'chirish
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={`«${deleting?.name}» ofisini o'chirasizmi?`}
        description="Bu amalni qaytarib bo'lmaydi. Ofis o'chirilgach, unga bog'liq check-in radius tekshiruvi ishlamaydi."
        confirmLabel="O'chirish"
        destructive
        loading={deleteOffice.isPending}
        onConfirm={() => {
          if (!deleting) return;
          deleteOffice.mutate(deleting.id, {
            onSuccess: () => {
              toast.success("Ofis o'chirildi.");
              setDeleting(null);
            },
          });
        }}
      />
    </div>
  );
}
