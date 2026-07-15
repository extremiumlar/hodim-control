import { useEffect, useState } from "react";
import { api, Office } from "../lib/api";

const EMPTY = { name: "", latitude: "", longitude: "", radius_meters: "150" };

export default function Offices() {
  const [offices, setOffices] = useState<Office[]>([]);
  const [form, setForm] = useState(EMPTY);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      setOffices(await api.listOffices());
    } catch (e: any) {
      setMsg("❌ " + (e.message || "Yuklashda xatolik"));
    }
  }

  useEffect(() => {
    load();
  }, []);

  function myLocation() {
    if (!navigator.geolocation) {
      setMsg("❌ Brauzer geolokatsiyani qo'llab-quvvatlamaydi.");
      return;
    }
    setMsg("Joylashuv aniqlanmoqda...");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setForm((f) => ({
          ...f,
          latitude: pos.coords.latitude.toFixed(6),
          longitude: pos.coords.longitude.toFixed(6),
        }));
        setMsg("✅ Joylashuv olindi — nom bering va saqlang.");
      },
      (e) => setMsg("❌ GPS xato: " + e.message),
      { enableHighAccuracy: true, timeout: 10000 }
    );
  }

  async function save() {
    if (!form.name.trim() || !form.latitude || !form.longitude) {
      setMsg("❌ Nom va koordinatalar to'ldirilishi shart.");
      return;
    }
    setBusy(true);
    setMsg("");
    try {
      const data = {
        name: form.name.trim(),
        latitude: parseFloat(form.latitude),
        longitude: parseFloat(form.longitude),
        radius_meters: parseInt(form.radius_meters, 10) || 150,
        is_active: true,
      };
      if (editingId != null) {
        await api.updateOffice(editingId, data);
        setMsg("✅ Ofis yangilandi.");
      } else {
        await api.createOffice(data);
        setMsg("✅ Ofis qo'shildi.");
      }
      setForm(EMPTY);
      setEditingId(null);
      await load();
    } catch (e: any) {
      setMsg("❌ " + (e.message || "Saqlashda xatolik"));
    } finally {
      setBusy(false);
    }
  }

  function startEdit(o: Office) {
    setEditingId(o.id);
    setForm({
      name: o.name,
      latitude: String(o.latitude),
      longitude: String(o.longitude),
      radius_meters: String(o.radius_meters),
    });
  }

  async function toggleActive(o: Office) {
    try {
      await api.updateOffice(o.id, { is_active: !o.is_active });
      await load();
    } catch (e: any) {
      setMsg("❌ " + (e.message || "Xatolik"));
    }
  }

  async function remove(o: Office) {
    if (!window.confirm(`«${o.name}» ofisini o'chirasizmi?`)) return;
    try {
      await api.deleteOffice(o.id);
      await load();
    } catch (e: any) {
      setMsg("❌ " + (e.message || "Xatolik"));
    }
  }

  const input = "border border-slate-300 rounded-md px-3 py-2 text-sm w-full";

  return (
    <div className="space-y-6 max-w-3xl">
      <h1 className="text-xl font-semibold">Ofislar (davomat GPS)</h1>
      <p className="text-sm text-slate-500">
        Xodim «Keldim/Ketdim» qilganda joylashuvi shu ofislardan biriga (radius ichida) tushishi shart.
      </p>

      {/* Forma */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-3">
        <h2 className="font-semibold">{editingId != null ? "Ofisni tahrirlash" : "Yangi ofis"}</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <input
            className={input}
            placeholder="Nomi (masalan: Bosh ofis)"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <input
            className={input}
            placeholder="Radius (metr)"
            type="number"
            value={form.radius_meters}
            onChange={(e) => setForm({ ...form, radius_meters: e.target.value })}
          />
          <input
            className={input}
            placeholder="Kenglik (latitude)"
            value={form.latitude}
            onChange={(e) => setForm({ ...form, latitude: e.target.value })}
          />
          <input
            className={input}
            placeholder="Uzunlik (longitude)"
            value={form.longitude}
            onChange={(e) => setForm({ ...form, longitude: e.target.value })}
          />
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={myLocation}
            className="px-4 py-2 rounded-md border border-slate-300 text-sm hover:bg-slate-50"
          >
            📍 Mening joyim
          </button>
          <button
            onClick={save}
            disabled={busy}
            className="px-4 py-2 rounded-md bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
          >
            {busy ? "Saqlanmoqda..." : editingId != null ? "Yangilash" : "Qo'shish"}
          </button>
          {editingId != null && (
            <button
              onClick={() => {
                setEditingId(null);
                setForm(EMPTY);
              }}
              className="px-4 py-2 rounded-md text-sm text-slate-500 hover:bg-slate-100"
            >
              Bekor
            </button>
          )}
        </div>
        {msg && <div className="text-sm">{msg}</div>}
      </div>

      {/* Ro'yxat */}
      <div className="bg-white border border-slate-200 rounded-xl p-4">
        <h2 className="font-semibold mb-3">Mavjud ofislar ({offices.length})</h2>
        {offices.length === 0 && (
          <div className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
            ⚠️ Hali ofis yo'q — xodimlar check-in qila olmaydi. Yuqoridan qo'shing.
          </div>
        )}
        <ul className="divide-y divide-slate-100">
          {offices.map((o) => (
            <li key={o.id} className="py-3 flex items-center justify-between gap-3">
              <div>
                <div className="font-medium">
                  {o.name}{" "}
                  {!o.is_active && (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-slate-200 text-slate-600">faolsiz</span>
                  )}
                </div>
                <div className="text-xs text-slate-500">
                  {o.latitude}, {o.longitude} · radius {o.radius_meters} m
                </div>
              </div>
              <div className="flex gap-2 text-sm shrink-0">
                <button onClick={() => startEdit(o)} className="text-indigo-600 hover:underline">
                  Tahrirlash
                </button>
                <button onClick={() => toggleActive(o)} className="text-amber-600 hover:underline">
                  {o.is_active ? "O'chirib qo'yish" : "Yoqish"}
                </button>
                <button onClick={() => remove(o)} className="text-rose-600 hover:underline">
                  O'chirish
                </button>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
