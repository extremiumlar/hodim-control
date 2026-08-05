/**
 * Ofislar xaritasi (UX-F, O1/O2 muammolari yechimi).
 *
 * Ilgari koordinata QO'LDA raqam bilan kiritilardi — lat/lng almashib ketsa
 * xato faqat xodim check-in qila olmaganda bilinardi; radius esa shunchaki
 * raqam edi ("150 m yetadimi?" — tasavvur yo'q). Endi:
 *   - har faol ofis xaritada marker + radius doirasi bilan;
 *   - xaritani BOSISH formaga koordinata yozadi;
 *   - tahrirlanayotgan ofis markeri sudrab suriladi (drag);
 *   - formadagi qiymatlar jonli doira bilan ko'rinadi.
 *
 * leaflet + OpenStreetMap — faqat shu sahifa chunk'ida (route lazy). Internet
 * bo'lmasa plitkalar chiqmaydi, lekin forma to'liq ishlayveradi (xarita —
 * qulaylik, majburiyat emas).
 */
import { useEffect } from "react";
import L from "leaflet";
import { Circle, MapContainer, Marker, TileLayer, Tooltip, useMap, useMapEvents } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import markerIcon from "leaflet/dist/images/marker-icon.png";
import markerIcon2x from "leaflet/dist/images/marker-icon-2x.png";
import markerShadow from "leaflet/dist/images/marker-shadow.png";
import { type Office } from "@/lib/api";

// Vite ostida leaflet'ning default marker rasmlari yo'qolib qoladi (u yo'lni
// runtime'da o'zi taxmin qiladi) — aniq URL'lar bilan tuzatamiz.
L.Icon.Default.mergeOptions({
  iconUrl: markerIcon,
  iconRetinaUrl: markerIcon2x,
  shadowUrl: markerShadow,
});

const TASHKENT: [number, number] = [41.311081, 69.240562];

function ClickHandler({ onPick }: { onPick: (lat: number, lng: number) => void }) {
  useMapEvents({
    click: (e) => onPick(e.latlng.lat, e.latlng.lng),
  });
  return null;
}

/** Formadagi koordinata o'zgarsa (masalan «Mening joyim») xaritani o'sha yerga suradi. */
function Recenter({ lat, lng }: { lat: number | null; lng: number | null }) {
  const map = useMap();
  useEffect(() => {
    if (lat != null && lng != null && Number.isFinite(lat) && Number.isFinite(lng)) {
      map.panTo([lat, lng]);
    }
  }, [lat, lng, map]);
  return null;
}

export default function OfficeMap({
  offices,
  editingId,
  formLat,
  formLng,
  formRadius,
  onPick,
}: {
  offices: Office[];
  /** Tahrirlanayotgan ofis — uning markeri drag qilinadi. */
  editingId: number | null;
  /** Formadagi joriy qiymatlar (yangi ofis yoki tahrir) — jonli doira. */
  formLat: number | null;
  formLng: number | null;
  formRadius: number;
  onPick: (lat: number, lng: number) => void;
}) {
  const hasForm = formLat != null && formLng != null && Number.isFinite(formLat) && Number.isFinite(formLng);
  const center: [number, number] = hasForm
    ? [formLat!, formLng!]
    : offices.length
      ? [Number(offices[0].latitude), Number(offices[0].longitude)]
      : TASHKENT;

  return (
    <div className="overflow-hidden rounded-xl border border-slate-200">
      <MapContainer center={center} zoom={15} className="h-80 w-full" scrollWheelZoom>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <ClickHandler onPick={onPick} />
        <Recenter lat={formLat} lng={formLng} />

        {/* Saqlangan ofislar (tahrirlanayotgani formadagi jonli doira bilan chiqadi) */}
        {offices
          .filter((o) => o.id !== editingId)
          .map((o) => (
            <Circle
              key={o.id}
              center={[Number(o.latitude), Number(o.longitude)]}
              radius={o.radius_meters}
              pathOptions={{
                color: o.is_active ? "#10b981" : "#94a3b8",
                fillColor: o.is_active ? "#10b981" : "#94a3b8",
                fillOpacity: 0.12,
                weight: 2,
              }}
            >
              <Tooltip direction="top" permanent>
                {o.name}
                {!o.is_active && " (faolsiz)"}
              </Tooltip>
            </Circle>
          ))}

        {/* Formadagi joriy nuqta — sudraladigan marker + jonli radius doirasi */}
        {hasForm && (
          <>
            <Marker
              position={[formLat!, formLng!]}
              draggable
              eventHandlers={{
                dragend: (e) => {
                  const p = (e.target as L.Marker).getLatLng();
                  onPick(p.lat, p.lng);
                },
              }}
            />
            <Circle
              center={[formLat!, formLng!]}
              radius={formRadius || 0}
              pathOptions={{
                color: "#4f46e5",
                fillColor: "#4f46e5",
                fillOpacity: 0.15,
                weight: 2,
                dashArray: "6 4",
              }}
            />
          </>
        )}
      </MapContainer>
      <p className="border-t border-slate-200 bg-slate-50 px-3 py-1.5 text-xs text-slate-500">
        Xaritani <b>bosing</b> — koordinata formaga yoziladi; markerni <b>sudrab</b> aniqlashtiring.
        Punktir doira — formadagi joriy radius.
      </p>
    </div>
  );
}
