import { useCallback, useEffect, useRef, useState } from "react";
import { Navigate } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { BRAND_NAME } from "@/lib/brand";

declare global {
  interface Window {
    onTelegramAuth?: (user: Record<string, string | number>) => void;
  }
}

const BOT_USERNAME = import.meta.env.VITE_TELEGRAM_LOGIN_BOT_USERNAME;
const DEV_MODE = import.meta.env.VITE_DEBUG === "true";

const POLL_INTERVAL_MS = 2500;

export default function Login() {
  const { user, loginWithToken } = useAuth();
  const widgetRef = useRef<HTMLDivElement>(null);
  const [devTelegramId, setDevTelegramId] = useState("");
  const [loggingIn, setLoggingIn] = useState(false);
  // pairingCode — foydalanuvchi BOTGA yozadigan 4 raqamli kod. Asosiy yo'lda
  // u sahifada KO'RINMAYDI: bot ochilganda server kodni foydalanuvchining
  // MOBIL ILOVASIGA push bilan yuboradi (2026-08-05 talabi). showCode faqat
  // zaxira holatda true bo'ladi — push qurilma topilmasa (poll'dagi
  // code_delivery "screen"ga tushsa) kod shu yerda ochiladi, aks holda
  // ilovasiz foydalanuvchi saytga umuman kira olmay qolardi.
  const [botLogin, setBotLogin] = useState<{
    token: string;
    deepLink: string;
    pairingCode: string;
    showCode: boolean;
  } | null>(null);
  const [botStarting, setBotStarting] = useState(false);
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!BOT_USERNAME || !widgetRef.current) return;

    window.onTelegramAuth = async (tgUser) => {
      try {
        const { access_token, user } = await api.telegramLogin(tgUser);
        loginWithToken(access_token, user);
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "Kirishda xatolik");
      }
    };

    const script = document.createElement("script");
    script.src = "https://telegram.org/js/telegram-widget.js?22";
    script.async = true;
    script.setAttribute("data-telegram-login", BOT_USERNAME);
    script.setAttribute("data-size", "large");
    script.setAttribute("data-onauth", "onTelegramAuth(user)");
    script.setAttribute("data-request-access", "write");
    widgetRef.current.appendChild(script);
  }, [loginWithToken]);

  // ── Bot orqali kirish (deep-link) — telegram.org skriptiga ZAXIRA ──
  // Widget telegram.org'dan skript yuklaydi; u bloklansa yoki sekinlashsa
  // saytga hech kim kira olmasdi. Bu yo'lda faqat bot kerak.
  const stopPolling = useCallback(() => {
    if (pollTimer.current) {
      clearInterval(pollTimer.current);
      pollTimer.current = null;
    }
  }, []);

  useEffect(() => stopPolling, [stopPolling]);

  const checkOnce = useCallback(
    async (loginToken: string) => {
      try {
        const res = await api.appLoginPoll(loginToken);
        if (res.status === "confirmed" && res.token) {
          stopPolling();
          loginWithToken(res.token.access_token, res.token.user);
        } else if (res.status === "pending" && res.code_delivery === "screen") {
          // Push qurilma topilmadi — server kodni "screen" rejimiga tushirdi,
          // endi uni sahifada ko'rsatamiz (funksional yangilash: checkOnce
          // yopilmasida botLogin eskirgan bo'lishi mumkin).
          setBotLogin((prev) => (prev && !prev.showCode ? { ...prev, showCode: true } : prev));
        } else if (res.status === "expired") {
          stopPolling();
          setBotLogin(null);
          toast.error("Havola muddati o'tdi (5 daqiqa). Qaytadan urinib ko'ring.");
        }
      } catch {
        stopPolling();
        setBotLogin(null);
        toast.error("Server bilan aloqa uzildi.");
      }
    },
    [loginWithToken, stopPolling]
  );

  const startBotLogin = async () => {
    stopPolling();
    setBotStarting(true);
    // Bot AVTOMATIK ochilishi uchun yangi oynani klik gestining o'zida
    // SINXRON ochamiz (bo'sh holda), manzilni token kelgach yozamiz —
    // await'dan keyin window.open chaqirilsa popup-bloker to'sib qo'yadi.
    // Yangi oynada ochish shart: shu sahifa tirik qolib poll davom etadi.
    const botWindow = window.open("", "_blank");
    try {
      const { login_token, deep_link, pairing_code } = await api.appLoginStart();
      setBotLogin({
        token: login_token,
        deepLink: deep_link,
        pairingCode: pairing_code,
        showCode: false,
      });
      if (botWindow) botWindow.location.href = deep_link;
      pollTimer.current = setInterval(() => void checkOnce(login_token), POLL_INTERVAL_MS);
    } catch (e) {
      botWindow?.close();
      toast.error(e instanceof Error ? e.message : "Kirishni boshlab bo'lmadi");
    } finally {
      setBotStarting(false);
    }
  };

  // Telefonda xodim Telegram'ga o'tib qaytganda darhol tekshiramiz — interval
  // kutib turishi (2.5s) o'rniga qaytish bilan login yakunlanadi. Mobil
  // brauzerlar fon tab'dagi taymerlarni sekinlashtiradi, shuning uchun ham
  // kerak.
  useEffect(() => {
    if (!botLogin) return;
    const onVisible = () => {
      if (document.visibilityState === "visible") void checkOnce(botLogin.token);
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [botLogin, checkOnce]);

  if (user) return <Navigate to="/" replace />;

  const handleDevLogin = async () => {
    setLoggingIn(true);
    try {
      const { access_token, user } = await api.devLogin(Number(devTelegramId));
      loginWithToken(access_token, user);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Kirishda xatolik");
    } finally {
      setLoggingIn(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="text-center">
          <CardTitle className="text-xl">{BRAND_NAME}</CardTitle>
        </CardHeader>
        <CardContent className="text-center">
          {BOT_USERNAME ? (
            <div ref={widgetRef} className="mb-4 flex justify-center" />
          ) : (
            <p className="mb-4 text-sm text-slate-500">
              TELEGRAM_LOGIN_BOT_USERNAME sozlanmagan — Telegram Login Widget ko'rsatilmayapti.
            </p>
          )}

          {/* Bot orqali kirish — widget ishlamasa ham (telegram.org bloklansa,
              sekinlashsa yoki skript yuklanmasa) ishlaydigan yo'l. */}
          {botLogin ? (
            <div className="space-y-3 rounded-xl border border-blue-200 bg-blue-50 p-3 text-left">
              <p className="text-sm text-slate-700">
                <span className="font-semibold">1.</span> Telegram bot avtomatik ochiladi
                (ochilmasa pastdagi tugmani bosing)
                <br />
                <span className="font-semibold">2.</span> Mobil ilovangizga kelgan 4 raqamli
                kodni botga yozing
                <br />
                <span className="font-semibold">3.</span> Shu sahifaga qaytsangiz — kirgan bo'lasiz
              </p>
              {/* Zaxira: push qurilma topilmaganda server kodni "screen"
                  rejimiga tushiradi va kod shu yerda ochiladi — aks holda
                  mobil ilovasiz foydalanuvchi saytga kira olmay qolardi. */}
              {botLogin.showCode && (
                <div className="rounded-lg border border-blue-300 bg-white py-3 text-center">
                  <p className="px-3 text-xs font-semibold text-blue-800">
                    Mobil ilovangiz topilmadi — botga shu kodni yozing
                  </p>
                  <p className="text-4xl font-bold tracking-[0.5em] text-blue-900 [text-indent:0.5em]">
                    {botLogin.pairingCode}
                  </p>
                  <p className="mt-1 px-3 text-xs text-slate-500">
                    Kodni hech kimga aytmang — u faqat shu oynaga kirish uchun.
                  </p>
                </div>
              )}
              {/* Oddiy havola, window.open EMAS: (1) popup-blokerga tushmaydi,
                  (2) target=_blank bilan sayt TIRIK qoladi va poll davom etadi.
                  O'sha oynada ochilsa, sahifa Telegram'ga o'tib ketib poll
                  halqasi o'lardi va qaytganda login yakunlanmasdi. */}
              <a
                href={botLogin.deepLink}
                target="_blank"
                rel="noreferrer"
                className="block w-full rounded-md bg-blue-600 px-4 py-3 text-center text-sm font-semibold text-white hover:bg-blue-700"
              >
                Botni ochish
              </a>
              <div className="flex items-center justify-between text-xs text-slate-500">
                <span className="flex items-center gap-1.5">
                  <span className="h-2 w-2 animate-pulse rounded-full bg-blue-500" />
                  Tasdiqlash kutilmoqda…
                </span>
                <button
                  onClick={() => {
                    setBotLogin(null);
                    void startBotLogin();
                  }}
                  className="underline hover:text-slate-700"
                >
                  Qaytadan
                </button>
              </div>
            </div>
          ) : (
            <Button
              variant={BOT_USERNAME ? "outline" : "default"}
              className="w-full"
              disabled={botStarting}
              onClick={startBotLogin}
            >
              {botStarting ? "Havola olinmoqda…" : "Bot orqali kirish"}
            </Button>
          )}

          {DEV_MODE && (
            <>
              <Separator className="my-4" />
              <p className="mb-2 text-xs text-amber-600">
                Dev-login (faqat lokal sinov uchun, DEBUG=true bo'lganda ishlaydi)
              </p>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  handleDevLogin();
                }}
                className="space-y-2"
              >
                <Input
                  type="text"
                  placeholder="Telegram ID"
                  value={devTelegramId}
                  onChange={(e) => setDevTelegramId(e.target.value)}
                />
                <Button type="submit" disabled={loggingIn} className="w-full">
                  {loggingIn ? "Kirilmoqda..." : "Dev sifatida kirish"}
                </Button>
              </form>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
