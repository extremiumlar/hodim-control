/**
 * Kabinet bo'limlarining umumiy ekrani — `/view?path=/me/schedule&title=Ish jadvali`.
 *
 * NEGA BITTA EKRAN: bo'limlar (ish jadvali, oylik, normam, rejam, KPI, lidlar,
 * vazifalar, statistika, sababli kun) ilova tomonida BIR XIL ishni qiladi —
 * saytning tegishli sahifasini WebView'da ochish. Har biriga alohida fayl
 * yozilsa, to'qqizta deyarli bir xil nusxa paydo bo'lardi va yangi bo'lim
 * qo'shilganda yana bittasi.
 *
 * Sahifalarning O'ZI web'da yozilgan (`web/src/pages/Me*.tsx`) — ya'ni sayt
 * deploy qilinsa, ilovadagi bo'limlar ham darhol yangilanadi, APK'ni qayta
 * qurish shart emas. Bu ataylab tanlangan: xodimlarga har safar yangi APK
 * tarqatish qiyin (Samsung Auto Blocker va h.k. — MOBIL_ILOVA_REJASI.md 8.5).
 */
import { router, useLocalSearchParams } from "expo-router";
import { ActivityIndicator, Text, View } from "react-native";

import EmbeddedWeb, { Message, styles, useWebPhase } from "../components/EmbeddedWeb";

export default function ViewScreen() {
  const params = useLocalSearchParams<{ path?: string; title?: string }>();
  const { phase } = useWebPhase();

  const path = typeof params.path === "string" ? params.path : "";
  const title = typeof params.title === "string" ? params.title : "Bo'lim";

  // Faqat o'z saytimizning ichki yo'li ochilsin — parametr tashqaridan
  // (masalan deep-link orqali) kelib qolsa, ixtiyoriy manzil ochilmasin.
  if (!path.startsWith("/") || path.startsWith("//")) {
    return (
      <Message
        title="Bo'lim topilmadi"
        body="Ushbu bo'lim mavjud emas yoki havola noto'g'ri."
        actionLabel="Bosh sahifa"
        onAction={() => router.replace("/home")}
      />
    );
  }

  if (phase.kind === "loading") {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" />
        <Text style={styles.hint}>Yuklanmoqda...</Text>
      </View>
    );
  }

  if (phase.kind === "no-token" || phase.kind === "no-permission") {
    return (
      <Message
        title="Sessiya tugagan"
        body="Qaytadan kirishingiz kerak."
        actionLabel="Kirish"
        onAction={() => router.replace("/login")}
      />
    );
  }

  return <EmbeddedWeb path={path} title={title} token={phase.token} />;
}
