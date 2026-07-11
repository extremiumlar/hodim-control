"use client";
import dynamic from "next/dynamic";

// face-api (kamera/yuz) faqat brauzerda ishlaydi — serverда (SSR/prerender)
// yuklansa "TextEncoder is not a constructor" beradi. Shuning uchun sahifa
// mazmuni ssr:false bilan faqat klientда yuklanadi.
const FaceRegisterClient = dynamic(() => import("./FaceRegisterClient"), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center min-h-[40vh] text-slate-500">
      Yuklanmoqda...
    </div>
  ),
});

export default function FaceRegisterPage() {
  return <FaceRegisterClient />;
}
