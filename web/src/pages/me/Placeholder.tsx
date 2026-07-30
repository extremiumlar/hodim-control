/**
 * Vaqtinchalik "Tez orada" sahifasi — Bosqich 1 skeletoni.
 *
 * Bo'limlar marshrutga BIRDANIGA qo'shiladi, mazmuni esa Bosqich 4 da bittalab
 * to'ldiriladi. Shu yondashuv mobil ilovada ham qo'llangan
 * (mobile/app/home.tsx): xodim nima kelayotganini ko'radi, lekin bo'sh
 * sahifaga urilmaydi. Har bir sahifa tayyor bo'lgach, App.tsx'dagi shu
 * element haqiqiy sahifaga almashtiriladi.
 */
import { useLocation } from "react-router-dom";
import { Hourglass } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { sectionTitle } from "@/lib/employeeNav";

export default function Placeholder() {
  const { pathname } = useLocation();
  const title = sectionTitle(pathname) ?? "Bo'lim";

  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-3 p-8 text-center">
        <Hourglass className="h-10 w-10 text-slate-300" />
        <div>
          <h2 className="text-base font-semibold">{title}</h2>
          <p className="mt-1 text-sm text-slate-500">
            Bu bo'lim tez orada shu yerda ochiladi. Hozircha uni Telegram botdan
            ko'rishingiz mumkin.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
