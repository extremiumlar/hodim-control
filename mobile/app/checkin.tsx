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
  // Joylashuv natijasi ATAYLAB tekshirilmaydi — yuqoridagi izohga qarang.
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
  return <EmbeddedWeb path={CHECKIN_PATH} title="Davomat" token={phase.token} media />;
}
