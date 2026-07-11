"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { isAuthenticated } from "@/lib/api";

export default function Home() {
  const router = useRouter();
  useEffect(() => {
    router.replace(isAuthenticated() ? "/dashboard" : "/login");
  }, [router]);
  return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="text-slate-500">Yuklanmoqda...</div>
    </div>
  );
}
