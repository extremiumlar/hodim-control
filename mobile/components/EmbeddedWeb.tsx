/**
 * Sayt sahifasini ilova ichida ko'rsatadigan umumiy WebView qobig'i.
 *
 * NEGA UMUMIY: davomat (`app/checkin.tsx`) va kabinet bo'limlari
 * (`app/view.tsx`) bir xil ishni qiladi — JWT'ni inject qilish, yuqori panel,
 * yuklanish ko'rsatkichi, tashqi havolani tizim brauzeriga chiqarish, Android
 * "orqaga" tugmasi. Ikki joyda takrorlansa, biri tuzatilib ikkinchisi
 * eskirib qolardi (masalan token kaliti o'zgarsa davomat ishlab, kabinet
 * /login ga tashlab yuborardi).
 *
 * Sahifaga `?embed=1` qo'shiladi — sayt shunda o'z qobig'ini (header,
 * tab-bar, sidebar) chizmaydi, chunki ilovaning o'z navigatsiyasi bor
 * (`web/src/Layout.tsx`: useEmbedded).
 */
import { router } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  BackHandler,
  Linking,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { WebView, type WebViewNavigation } from "react-native-webview";

import { getStoredToken } from "../lib/api";
import { WEB_BASE_URL } from "../lib/config";

/** Sahifa yo'liga `embed=1` qo'shadi (yo'lda allaqachon `?` bo'lishi mumkin). */
function embedUrl(path: string): string {
  const sep = path.includes("?") ? "&" : "?";
  return `${WEB_BASE_URL}${path}${sep}embed=1`;
}

/**
 * Ruxsat etilgan YAGONA origin. Bir marta hisoblanadi va `onShouldStart`da
 * hamda `originWhitelist`da ishlatiladi — ikkalasi bir manbadan bo'lsin.
 */
const ALLOWED_ORIGIN = new URL(WEB_BASE_URL).origin;

export type WebPhase =
  | { kind: "loading" }
  | { kind: "no-permission" }
  | { kind: "no-token" }
  | { kind: "ready"; token: string };

export function Message({
  title,
  body,
  actionLabel,
  onAction,
}: {
  title: string;
  body: string;
  actionLabel: string;
  onAction: () => void;
}) {
  return (
    <View style={styles.center}>
      <Text style={styles.msgTitle}>{title}</Text>
      <Text style={styles.msgBody}>{body}</Text>
      <Pressable onPress={onAction} style={styles.btn}>
        <Text style={styles.btnText}>{actionLabel}</Text>
      </Pressable>
      <Pressable onPress={() => router.back()} style={styles.btnGhost}>
        <Text style={styles.btnGhostText}>Orqaga</Text>
      </Pressable>
    </View>
  );
}

/**
 * Tokenni o'qiydi va ekran holatini qaytaradi. `extraCheck` — ekranga xos
 * qo'shimcha shart (davomatda kamera/GPS ruxsati); `false` qaytarsa
 * "no-permission" holati chiqadi.
 */
export function useWebPhase(extraCheck?: () => Promise<boolean>): {
  phase: WebPhase;
  retry: () => void;
} {
  const [phase, setPhase] = useState<WebPhase>({ kind: "loading" });

  const prepare = useCallback(async () => {
    setPhase({ kind: "loading" });
    if (extraCheck && !(await extraCheck())) {
      setPhase({ kind: "no-permission" });
      return;
    }
    const token = await getStoredToken();
    setPhase(token ? { kind: "ready", token } : { kind: "no-token" });
    // extraCheck ataylab bog'liqlikda emas: chaqiruvchi uni har renderda
    // qayta yaratsa, bu effekt cheksiz aylanardi.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    void prepare();
  }, [prepare]);

  return { phase, retry: () => void prepare() };
}

export default function EmbeddedWeb({
  path,
  title,
  token,
  /** Davomat uchun: kamera oqimi va geolokatsiya (boshqa sahifalarga kerak emas). */
  media = false,
}: {
  path: string;
  title: string;
  token: string;
  media?: boolean;
}) {
  const [pageLoading, setPageLoading] = useState(true);
  // UX2-MC4: tarmoq xatosi endi ishlov ko'radi — ilgari Android'ning
  // inglizcha tizim xato sahifasi yoki oq ekran ko'rinardi (aynan ofis
  // eshigi oldida, zaif tarmoqda).
  const [loadError, setLoadError] = useState(false);
  const webRef = useRef<WebView>(null);

  // Android "orqaga": ekrandan chiqadi. Usiz ilova butunlay yopilib ketardi.
  useEffect(() => {
    const sub = BackHandler.addEventListener("hardwareBackPress", () => {
      router.back();
      return true;
    });
    return () => sub.remove();
  }, []);

  // Sayt JWT'ni localStorage["access_token"]dan o'qiydi (web/src/lib/auth.tsx) —
  // sahifa skriptlari ishga tushishidan OLDIN yozamiz, aks holda /login ga
  // yo'naltiriladi.
  //
  // ⚠️ BU YERDA QOLGAN XAVF (kod bilan to'liq yopib bo'lmaydi):
  // `injectedJavaScriptBeforeContentLoaded` nativ tomonda `onPageStarted`da
  // chaqiriladi, ya'ni HAR sahifa yuklanishida — faqat birinchisida emas.
  // Origin tekshiruvi esa JS callback'i orqali ishlaydi va nativ tomon uni
  // atigi 250 ms kutadi: javob yetib bormasa navigatsiyaga RUXSAT berib
  // yuboradi ("defaulting to allow loading", RNCWebViewClient.java:112-114).
  // Ya'ni JS thread band bo'lgan lahzada tekshiruv umuman ishlamay qolishi
  // mumkin, va o'sha paytda token begona sahifaga yozilardi.
  //
  // Buni butunlay yopishning YAGONA yo'li — bu yerga 30 kunlik JWT'ni umuman
  // kiritmaslik: WebView uchun qisqa muddatli (bir necha daqiqalik), alohida
  // token berish. Bu backend o'zgarishini talab qiladi, shuning uchun alohida
  // ish sifatida rejalashtirilgan (audit hisoboti, B3-5).
  const injectedToken = `
    (function () {
      try {
        window.localStorage.setItem('access_token', ${JSON.stringify(token)});
      } catch (e) {}
      true;
    })();
  `;

  // WebView faqat o'z saytimizda qolsin: sahifadagi tashqi havola ilova
  // ichida ochilib qolmasin (tizim brauzerida ochilsin).
  //
  // XAVFSIZLIK — nega `startsWith` EMAS, `origin` solishtiriladi:
  // `startsWith("https://nuriddin-building.uz")` ORIGIN tekshiruvi emas.
  // Unga quyidagilar ham mos keladi va hujumchi ularni bemalol ro'yxatdan
  // o'tkaza oladi:
  //     https://nuriddin-building.uz.evil.com/
  //     https://nuriddin-building.uzevil.com/
  // JWT esa `injectedJavaScriptBeforeContentLoaded` orqali HAR sahifa
  // yuklanishida localStorage'ga yoziladi (react-native-webview'da u
  // `onPageStarted`da chaqiriladi, faqat birinchi yuklanishda emas) — ya'ni
  // shunday domenga o'tilsa, xodimning tokeni TO'G'RIDAN-TO'G'RI hujumchining
  // sahifasiga yozilardi.
  const onShouldStart = (req: WebViewNavigation): boolean => {
    let origin: string | null = null;
    try {
      origin = new URL(req.url).origin;
    } catch {
      return false; // manzilni parse qilib bo'lmasa — ishonmaymiz
    }
    if (origin === ALLOWED_ORIGIN) return true;

    // Tashqi havola tizim brauzerida ochiladi — LEKIN faqat http(s).
    // Aks holda sahifa `intent://`, `file://` yoki ilovaning o'z
    // `hodimlarapp://` sxemasini OS'ga uzatib, boshqa ilovalarni qo'zg'atishi
    // yoki o'zimizning deep-link'imizni chaqirishi mumkin edi.
    if (origin.startsWith("http://") || origin.startsWith("https://")) {
      void Linking.openURL(req.url);
    }
    return false;
  };

  return (
    <View style={styles.flex}>
      <View style={styles.bar}>
        <Pressable onPress={() => router.back()} hitSlop={12}>
          <Text style={styles.back}>‹ Orqaga</Text>
        </Pressable>
        <Text style={styles.barTitle} numberOfLines={1}>
          {title}
        </Text>
        <Pressable onPress={() => webRef.current?.reload()} hitSlop={12}>
          <Text style={styles.reload}>Yangilash</Text>
        </Pressable>
      </View>

      <WebView
        ref={webRef}
        source={{ uri: embedUrl(path) }}
        injectedJavaScriptBeforeContentLoaded={injectedToken}
        onShouldStartLoadWithRequest={onShouldStart}
        // Qo'pol old-filtr. DIQQAT — bu YETARLI EMAS va yuqoridagi
        // `onShouldStart`ning o'rnini BOSMAYDI:
        //   - u nativ emas, JS tomonda ishlaydi (WebViewShared.tsx);
        //   - `originWhitelistToRegex` naqshni `^...` bilan boshlaydi, LEKIN
        //     oxiriga `$` QO'YMAYDI — ya'ni bu ham PREFIKS moslik va
        //     "https://nuriddin-building.uz.evil.com" unga ham mos keladi.
        // Sukut qiymati ['http://*','https://*'] bo'lgani uchun baribir
        // foydasi bor: begona sxemalar va butunlay boshqa domenlar shu yerda
        // kesiladi. Haqiqiy himoya — `onShouldStart`dagi origin TENGLIGI.
        originWhitelist={[ALLOWED_ORIGIN]}
        // `window.open()` / target="_blank" popup'i `WebViewClient`SIZ yangi
        // WebView yaratadi — ya'ni `onShouldStartLoadWithRequest` umuman
        // chaqirilmaydi va sahifa ilova ichida KO'RINMAS holda yuklanadi.
        // Bu bilan yuqoridagi origin tekshiruvini butunlay chetlab o'tish
        // mumkin edi.
        setSupportMultipleWindows={false}
        // Faqat o'z saytimiz ochiladi — uchinchi tomon cookie'lari keraksiz,
        // ular esa yuqoridagi popup/download yo'llari orqali begona kontentga
        // sessiya biriktirib yuborishi mumkin.
        thirdPartyCookiesEnabled={false}
        // Standart yuklovchi sayt COOKIE'larini biriktirib, faylni ommaviy
        // Downloads papkasiga so'rovsiz yozadi. Bo'limlarning hech biri fayl
        // yuklamaydi, shuning uchun butunlay to'xtatamiz.
        onFileDownload={() => undefined}
        onLoadEnd={() => setPageLoading(false)}
        // UX2-MC4: tarmoq/HTTP xatolarida o'zbekcha ekran + «Qayta urinish».
        onError={() => {
          setPageLoading(false);
          setLoadError(true);
        }}
        onHttpError={(e) => {
          // 5xx — server yotibdi; 4xx sahifa o'zi ko'rsatadi (masalan 404 SPA
          // fallback bilan index.html qaytaradi, xato emas).
          if (e.nativeEvent.statusCode >= 500) {
            setPageLoading(false);
            setLoadError(true);
          }
        }}
        // UX2-MC5: sayt tokeni eskirib /login'ga yo'naltirsa — saytning
        // ikkinchi (chalkash) login sahifasi o'rniga ilovaning o'z kirish
        // ekrani ochiladi.
        onNavigationStateChange={(nav) => {
          try {
            if (new URL(nav.url).pathname === "/login") {
              router.replace("/login" as never);
            }
          } catch {
            // parse bo'lmasa e'tiborsiz
          }
        }}
        mediaPlaybackRequiresUserAction={!media}
        allowsInlineMediaPlayback={media}
        geolocationEnabled={media}
        javaScriptEnabled
        domStorageEnabled
        style={styles.flex}
      />

      {pageLoading && !loadError && (
        <View style={styles.overlay}>
          <ActivityIndicator size="large" />
          <Text style={styles.hint}>Yuklanmoqda...</Text>
        </View>
      )}

      {loadError && (
        <View style={styles.overlay}>
          <Message
            title="Sahifa ochilmadi"
            body="Internet aloqasi yo'q yoki server javob bermayapti. Tarmoqni tekshirib, qayta urinib ko'ring."
            actionLabel="Qayta urinish"
            onAction={() => {
              setLoadError(false);
              setPageLoading(true);
              webRef.current?.reload();
            }}
          />
        </View>
      )}
    </View>
  );
}

export const styles = StyleSheet.create({
  flex: { flex: 1 },
  center: { flex: 1, alignItems: "center", justifyContent: "center", padding: 24, gap: 12 },
  hint: { color: "#555", fontSize: 14 },
  bar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingTop: 48,
    paddingBottom: 12,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: "#e2e8f0",
    gap: 12,
  },
  // flexShrink — uzun sarlavha ("Lidlar statistikasi") yon tugmalarni
  // ekrandan chiqarib yubormasligi uchun
  barTitle: { flexShrink: 1, fontSize: 16, fontWeight: "700" },
  back: { fontSize: 16, color: "#2563eb" },
  reload: { fontSize: 14, color: "#2563eb" },
  overlay: {
    position: "absolute",
    top: 84,
    left: 0,
    right: 0,
    bottom: 0,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#fff",
    gap: 12,
  },
  msgTitle: { fontSize: 18, fontWeight: "700", textAlign: "center" },
  msgBody: { fontSize: 14, color: "#555", textAlign: "center", lineHeight: 20 },
  btn: {
    backgroundColor: "#2563eb",
    paddingHorizontal: 20,
    paddingVertical: 12,
    borderRadius: 12,
    marginTop: 8,
  },
  btnText: { color: "#fff", fontWeight: "600", fontSize: 15 },
  btnGhost: { padding: 12 },
  btnGhostText: { color: "#555", fontSize: 15 },
});
