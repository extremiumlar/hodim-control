/**
 * Davomat (Keldim/Ketdim) ekrani — MOBIL_ILOVA_REJASI.md 4.2-band.
 *
 * NEGA WebView: yuz vektori (128-o'lchovli descriptor) face-api.js bilan
 * BRAUZERDA hisoblanadi (web/src/lib/face.ts) va serverga tayyor vektor
 * ketadi — /me/check-in rasm qabul qilmaydi. React Native'da DOM/canvas yo'q,
 * ya'ni o'sha kodni nativ qayta yozib bo'lmaydi. Boshqa modelga o'tsak
 * saqlangan barcha descriptorlar yaroqsiz bo'lib, HAMMA xodim yuzini
 * qaytadan ro'yxatdan o'tkazishi kerak bo'lardi. Shuning uchun mavjud
 * sahifani WebView'da ochamiz: descriptorlar mos, backend o'zgarmaydi va
 * web'dagi tiriklik yaxshilanishlari ilovaga avtomatik tegadi.
 *
 * Brauzerdagi asosiy muammo — kamera/GPS ruxsati — bu yerda hal bo'ladi:
 * ruxsatni NATIV so'raymiz, WebView esa ilovaning ruxsatidan foydalanadi.
 */
import { router } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  BackHandler,
  Linking,
  PermissionsAndroid,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { WebView, type WebViewNavigation } from "react-native-webview";

import { getStoredToken } from "../lib/api";
import { WEB_BASE_URL } from "../lib/config";

const CHECKIN_PATH = "/embed/check-in";

type Phase =
  | { kind: "loading" }
  | { kind: "no-permission" }
  | { kind: "no-token" }
  | { kind: "ready"; token: string };

async function requestPermissions(): Promise<boolean> {
  if (Platform.OS !== "android") return true;
  const camera = PermissionsAndroid.PERMISSIONS.CAMERA;
  const fine = PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION;
  const res = await PermissionsAndroid.requestMultiple([camera, fine]);
  const granted = PermissionsAndroid.RESULTS.GRANTED;
  return res[camera] === granted && res[fine] === granted;
}

export default function CheckInScreen() {
  const [phase, setPhase] = useState<Phase>({ kind: "loading" });
  const [pageLoading, setPageLoading] = useState(true);
  const webRef = useRef<WebView>(null);

  const prepare = useCallback(async () => {
    setPhase({ kind: "loading" });
    // Ruxsatni sahifa ochilishidan OLDIN so'raymiz: WebView getUserMedia'ni
    // chaqirganda ilovada ruxsat bo'lmasa, kamera jim rad etiladi va sahifa
    // "kamera topilmadi" deb noaniq xato beradi.
    if (!(await requestPermissions())) {
      setPhase({ kind: "no-permission" });
      return;
    }
    const token = await getStoredToken();
    if (!token) {
      setPhase({ kind: "no-token" });
      return;
    }
    setPhase({ kind: "ready", token });
  }, []);

  useEffect(() => {
    void prepare();
  }, [prepare]);

  // Android "orqaga" tugmasi: WebView ichida tarix bo'lsa o'sha yerda orqaga,
  // aks holda ekrandan chiqadi (aks holda ilova butunlay yopilib ketardi).
  useEffect(() => {
    const sub = BackHandler.addEventListener("hardwareBackPress", () => {
      router.back();
      return true;
    });
    return () => sub.remove();
  }, []);

  if (phase.kind === "loading") {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" />
        <Text style={styles.hint}>Tayyorlanmoqda...</Text>
      </View>
    );
  }

  if (phase.kind === "no-permission") {
    return (
      <Message
        title="Kamera va joylashuv ruxsati kerak"
        body={
          "Keldim/Ketdim uchun yuzni tekshirish (kamera) va ofisga yaqinligini " +
          "aniqlash (joylashuv) shart. Ruxsatni sozlamalardan yoqing."
        }
        actionLabel="Sozlamalarni ochish"
        onAction={() => void Linking.openSettings()}
      />
    );
  }

  if (phase.kind === "no-token") {
    return (
      <Message
        title="Sessiya tugagan"
        body="Qaytadan kirishingiz kerak."
        actionLabel="Kirish"
        onAction={() => router.replace("/login")}
      />
    );
  }

  // Web ilova JWT'ni localStorage["access_token"]dan o'qiydi
  // (web/src/lib/auth.tsx) — sahifa skriptlari ishga tushishidan OLDIN
  // yozamiz, aks holda /login ga yo'naltiriladi.
  const injectedToken = `
    (function () {
      try {
        window.localStorage.setItem('access_token', ${JSON.stringify(phase.token)});
      } catch (e) {}
      true;
    })();
  `;

  // WebView'ni faqat o'z saytimizda ushlab turamiz: sahifadagi tashqi havola
  // ilova ichida ochilib qolmasin (tizim brauzerida ochilsin).
  const onShouldStart = (req: WebViewNavigation): boolean => {
    if (req.url.startsWith(WEB_BASE_URL)) return true;
    void Linking.openURL(req.url);
    return false;
  };

  return (
    <View style={styles.flex}>
      <View style={styles.bar}>
        <Pressable onPress={() => router.back()} hitSlop={12}>
          <Text style={styles.back}>‹ Orqaga</Text>
        </Pressable>
        <Text style={styles.barTitle}>Davomat</Text>
        <Pressable onPress={() => webRef.current?.reload()} hitSlop={12}>
          <Text style={styles.reload}>Yangilash</Text>
        </Pressable>
      </View>

      <WebView
        ref={webRef}
        source={{ uri: `${WEB_BASE_URL}${CHECKIN_PATH}` }}
        injectedJavaScriptBeforeContentLoaded={injectedToken}
        onShouldStartLoadWithRequest={onShouldStart}
        onLoadEnd={() => setPageLoading(false)}
        // Kamera oqimi sahifa ichida, foydalanuvchi bosishini kutmasdan
        // ishga tushishi kerak (Face ID avtomatik boshlanadi).
        mediaPlaybackRequiresUserAction={false}
        allowsInlineMediaPlayback
        // GPS: sahifa navigator.geolocation ishlatadi (web/src/pages/CheckIn.tsx)
        geolocationEnabled
        javaScriptEnabled
        domStorageEnabled
        style={styles.flex}
      />

      {pageLoading && (
        <View style={styles.overlay}>
          <ActivityIndicator size="large" />
          <Text style={styles.hint}>Yuklanmoqda...</Text>
        </View>
      )}
    </View>
  );
}

function Message({
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

const styles = StyleSheet.create({
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
  },
  barTitle: { fontSize: 16, fontWeight: "700" },
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
