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
 *
 * WebView qobig'i `components/EmbeddedWeb.tsx` da — kabinet bo'limlari bilan
 * bir xil (token inject, orqaga paneli, tashqi havola himoyasi).
 */
import { router } from "expo-router";
import { ActivityIndicator, Linking, PermissionsAndroid, Platform, Text, View } from "react-native";

import EmbeddedWeb, { Message, styles, useWebPhase } from "../components/EmbeddedWeb";

// Layout'SIZ marshrut (web/src/App.tsx) — ilovaning o'z paneli bor.
const CHECKIN_PATH = "/embed/check-in";

async function requestPermissions(): Promise<boolean> {
  if (Platform.OS !== "android") return true;
  const camera = PermissionsAndroid.PERMISSIONS.CAMERA;
  const fine = PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION;
  const res = await PermissionsAndroid.requestMultiple([camera, fine]);
  const granted = PermissionsAndroid.RESULTS.GRANTED;
  return res[camera] === granted && res[fine] === granted;
}

export default function CheckInScreen() {
  // Ruxsatni sahifa ochilishidan OLDIN so'raymiz: WebView getUserMedia'ni
  // chaqirganda ilovada ruxsat bo'lmasa, kamera jim rad etiladi va sahifa
  // "kamera topilmadi" deb noaniq xato beradi.
  const { phase } = useWebPhase(requestPermissions);

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

  // media — kamera oqimi foydalanuvchi bosishini kutmasdan ishga tushsin
  // (Face ID avtomatik boshlanadi) va sahifa navigator.geolocation ishlatadi.
  return <EmbeddedWeb path={CHECKIN_PATH} title="Davomat" token={phase.token} media />;
}
