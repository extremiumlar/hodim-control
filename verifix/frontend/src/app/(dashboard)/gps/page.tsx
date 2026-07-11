"use client";
import { useState } from "react";

export default function GpsPage() {
  const [pos, setPos] = useState<GeolocationPosition | null>(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState<GeolocationPosition[]>([]);

  function getCoords() {
    setErr("");
    setLoading(true);
    if (!navigator.geolocation) {
      setErr("Brauzer geolokatsiyani qo'llab-quvvatlamaydi.");
      setLoading(false);
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (p) => {
        setPos(p);
        setHistory((h) => [p, ...h].slice(0, 5));
        setLoading(false);
      },
      (e) => {
        setErr(`Xato: ${e.message}`);
        setLoading(false);
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 },
    );
  }

  function copy(text: string) {
    navigator.clipboard.writeText(text);
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold">📍 GPS Koordinata</h1>
        <p className="text-slate-500 text-sm">
          Turgan joyingizning aniq koordinatasini olish (ofis uchun)
        </p>
      </div>

      <div className="card text-center">
        <button onClick={getCoords} disabled={loading} className="btn-primary text-lg px-8 py-4">
          {loading ? "Aniqlanmoqda..." : "📡 Joyimni aniqla"}
        </button>
        <p className="text-xs text-slate-400 mt-3">
          Telefondagi GPS aniqroq natija beradi (xona ichida bo'lsangiz 20-100m xato bo'lishi mumkin — tashqariga chiqib bosing)
        </p>
      </div>

      {err && (
        <div className="card bg-rose-50 border-rose-200 text-rose-700">
          {err}
        </div>
      )}

      {pos && (
        <div className="card space-y-4">
          <h2 className="font-semibold text-lg">Sizning joylashuvingiz</h2>

          <div className="grid grid-cols-2 gap-3">
            <div className="bg-slate-50 rounded-lg p-3">
              <div className="text-xs text-slate-500">Kenglik (latitude)</div>
              <div className="text-xl font-mono font-bold mt-1">{pos.coords.latitude.toFixed(6)}</div>
              <button onClick={() => copy(pos.coords.latitude.toFixed(6))}
                      className="text-xs text-primary-600 underline mt-1">📋 Nusxa</button>
            </div>
            <div className="bg-slate-50 rounded-lg p-3">
              <div className="text-xs text-slate-500">Uzunlik (longitude)</div>
              <div className="text-xl font-mono font-bold mt-1">{pos.coords.longitude.toFixed(6)}</div>
              <button onClick={() => copy(pos.coords.longitude.toFixed(6))}
                      className="text-xs text-primary-600 underline mt-1">📋 Nusxa</button>
            </div>
          </div>

          <div className="bg-emerald-50 rounded-lg p-3 border border-emerald-200">
            <div className="text-xs text-emerald-700 mb-1">Admin panel uchun (ikkalasi birga)</div>
            <div className="font-mono text-sm break-all">
              {pos.coords.latitude.toFixed(6)}, {pos.coords.longitude.toFixed(6)}
            </div>
            <button onClick={() => copy(`${pos.coords.latitude.toFixed(6)}, ${pos.coords.longitude.toFixed(6)}`)}
                    className="text-xs text-emerald-700 underline mt-1">📋 Hammasini nusxa olish</button>
          </div>

          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="bg-slate-50 rounded-lg p-3">
              <div className="text-xs text-slate-500">Aniqlik (accuracy)</div>
              <div className="font-semibold">±{Math.round(pos.coords.accuracy)} m</div>
            </div>
            <div className="bg-slate-50 rounded-lg p-3">
              <div className="text-xs text-slate-500">Olingan vaqt</div>
              <div className="font-semibold">{new Date(pos.timestamp).toLocaleTimeString("uz-UZ")}</div>
            </div>
          </div>

          <a
            href={`https://www.google.com/maps?q=${pos.coords.latitude},${pos.coords.longitude}`}
            target="_blank" rel="noreferrer"
            className="btn-ghost w-full text-center"
          >
            🗺 Google Maps'da ochish
          </a>
        </div>
      )}

      {history.length > 1 && (
        <div className="card">
          <h3 className="font-semibold mb-3 text-sm">Tarix</h3>
          <ul className="space-y-2 text-xs">
            {history.slice(1).map((p, i) => (
              <li key={i} className="flex justify-between border-b pb-1 last:border-0">
                <span className="font-mono">{p.coords.latitude.toFixed(6)}, {p.coords.longitude.toFixed(6)}</span>
                <span className="text-slate-400">±{Math.round(p.coords.accuracy)}m</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="card bg-blue-50 border-blue-200 text-blue-900 text-sm">
        <h3 className="font-semibold mb-2">💡 Ofisni sozlash uchun:</h3>
        <ol className="list-decimal ml-5 space-y-1">
          <li>Ofis ichidagi (yoki yaqinidagi) eng yaxshi GPS aniqlik joyiga boring</li>
          <li>Yuqoridagi tugmani bosib koordinatani oling</li>
          <li><a href="http://localhost:8000/admin" target="_blank" className="underline">Admin panelga</a> kiring → <b>Office locations</b> → <b>Bosh ofis</b></li>
          <li>Olgan koordinatani <b>Latitude</b> va <b>Longitude</b> ga yozing</li>
          <li><b>Radius</b>: ofis hajmiga qarab (200-500m yetarli)</li>
          <li>Save</li>
        </ol>
      </div>
    </div>
  );
}
