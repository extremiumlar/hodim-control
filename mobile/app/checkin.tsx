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
import { useState } from "react";
import {
  ActivityIndicator,
  Linking,
  PermissionsAndroid,
  Platform,
  Pressable,
  Text,
  View,
} from "react-native";

import EmbeddedWeb, { Message, styles, useWebPhase } from "../components/EmbeddedWeb";

// Layout'SIZ marshrut (web/src/App.tsx) — ilovaning o'z paneli bor.
const CHECKIN_PATH = "/embed/check-in";

// UX2-qoldiq #10: joylashuv rad etilganini modul darajasida eslab qolamiz —
// requestPermissions useWebPhase ichida chaqiriladi va natijaning joylashuv
// qismini komponentga boshqa yo'l bilan yetkaza olmaydi.
let locationDenied = false;

/**
 * Kamera va joylashuv ruxsatini so'raydi.
 *
 * FAQAT KAMERA MAJBURIY. Ilgari ikkalasi ham talab qilinardi va joylashuvni
 * rad etgan xodim shu ekranda to'xtab qolardi — lekin serverda «joylashuvsiz
 * check-in» ruxsati bor xodimlar bo'ladi (mobilograf, kuryer), ular uchun bu
 * to'siq mutlaqo asossiz edi: ilova ularni saytga umuman qo'ymasdi.
 *
 * Joylashuv rad etilsa sahifa baribir ochiladi va qaror SERVERDA chiqadi:
 * ruxsati bor xodim o'tadi, ruxsati yo'q xodim aniq xato oladi («Joylashuv
 * aniqlanmadi. GPS'ni yoqib qayta urinib ko'ring»). Ya'ni ruxsat qoidasi
 * yagona joyda — backendda — qoladi, ilovada takrorlanmaydi.
 */
async function requestPermissions(): Promise<boolean> {
  if (Platform.OS !== "android") return true;
  const camera = PermissionsAndroid.PERMISSIONS.CAMERA;
  const fine = PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION;
  const res = await PermissionsAndroid.requestMultiple([camera, fine]);
  // Joylashuv natijasi sahifani BLOKLAMAYDI (yuqoridagi izoh) — lekin #10:
  // rad etilganini eslab, ekranda doimiy ogohlantirish chizig'i ko'rsatamiz
  // (ilgari faqat yo'qolib ketadigan toast bor edi).
  locationDenied = res[fine] !== PermissionsAndroid.RESULTS.GRANTED;
  return res[camera] === PermissionsAndroid.RESULTS.GRANTED;
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
        title="Kamera ruxsati kerak"
        body={
          "Keldim/Ketdim uchun yuzni tekshirish shart — kamerasiz bu ishlamaydi. " +
          "Ruxsatni sozlamalardan yoqing."
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
  return (
    <View style={styles.flex}>
      {locationDenied && <LocationBanner />}
      <EmbeddedWeb path={CHECKIN_PATH} title="Davomat" token={phase.token} media />
    </View>
  );
}

/** #10: joylashuv rad etilgan xodimga DOIMIY ko'rsatma (toast yo'qolib ketardi). */
function LocationBanner() {
  const [hidden, setHidden] = useState(false);
  if (hidden) return null;
  return (
    <View
      style={{
        flexDirection: "row",
        alignItems: "center",
        gap: 8,
        backgroundColor: "#fef3c7",
        paddingHorizontal: 12,
        paddingVertical: 8,
        paddingTop: 44,
      }}
    >
      <Text style={{ flex: 1, fontSize: 12, color: "#92400e" }}>
        Joylashuv ruxsati berilmagan — «Keldim» GPS'siz o'tmasligi mumkin.
      </Text>
      <Pressable onPress={() => void Linking.openSettings()}>
        <Text style={{ fontSize: 12, fontWeight: "700", color: "#92400e" }}>Sozlamalar</Text>
      </Pressable>
      <Pressable onPress={() => setHidden(true)} hitSlop={8}>
        <Text style={{ fontSize: 14, color: "#92400e" }}>✕</Text>
      </Pressable>
    </View>
  );
}
