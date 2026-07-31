/**
 * Bildirishnoma sozlamalari — toifalarni yoqish/o'chirish.
 *
 * Toifalar ro'yxati va nomlari SERVERDAN keladi (`/me/push/settings`) —
 * ilova o'z nusxasini saqlamaydi. Sabab: standart qiymatlar ROLGA bog'liq va
 * server tomonda o'zgarishi mumkin; ilovada takrorlansa, yangi toifa
 * qo'shilganda eski APK uni ko'rsatmay qolardi.
 */
import { router } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  View,
} from "react-native";

import { getPushSettings, registerForPush, updatePushSettings, type PushSettings } from "../lib/push";

export default function NotificationsScreen() {
  const [settings, setSettings] = useState<PushSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState<string | null>(null);
  const [granted, setGranted] = useState<boolean | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setSettings(await getPushSettings());
    } catch {
      setError("Sozlamalarni yuklab bo'lmadi. Internetni tekshirib qayta urinib ko'ring.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    // Ekran ochilganda ruxsatni ham so'raymiz — foydalanuvchi aynan shu
    // yerda bildirishnoma haqida o'ylayapti, so'rov kutilmagan bo'lmaydi.
    void registerForPush().then(setGranted);
  }, [load]);

  async function toggle(category: string, value: boolean) {
    if (!settings) return;
    // Optimistik yangilash — switch darhol javob bersin; xato bo'lsa qaytaramiz.
    const previous = settings;
    setSettings({ ...settings, categories: { ...settings.categories, [category]: value } });
    setSaving(category);
    try {
      setSettings(await updatePushSettings({ [category]: value }));
    } catch {
      setSettings(previous);
      setError("Saqlanmadi — qayta urinib ko'ring.");
    } finally {
      setSaving(null);
    }
  }

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <View style={styles.bar}>
        <Pressable onPress={() => router.back()} hitSlop={12}>
          <Text style={styles.back}>‹ Orqaga</Text>
        </Pressable>
        <Text style={styles.barTitle}>Bildirishnomalar</Text>
        <View style={styles.barSpacer} />
      </View>

      {granted === false && (
        <View style={styles.warn}>
          <Text style={styles.warnText}>
            Bildirishnoma ruxsati berilmagan. Telefon sozlamalaridan «N.B hodimlar» uchun
            bildirishnomani yoqing — aks holda xabarlar faqat Telegram botga keladi.
          </Text>
        </View>
      )}

      {loading && (
        <View style={styles.center}>
          <ActivityIndicator size="large" />
        </View>
      )}

      {error && !loading && (
        <Pressable onPress={() => void load()} style={styles.warn}>
          <Text style={styles.warnText}>{error} (qayta urinish uchun bosing)</Text>
        </Pressable>
      )}

      {settings && (
        <>
          <View style={styles.card}>
            {Object.keys(settings.categories).map((key, i) => (
              <View key={key} style={[styles.row, i > 0 && styles.rowBorder]}>
                <Text style={styles.rowLabel}>{settings.labels[key] ?? key}</Text>
                <Switch
                  value={settings.categories[key]}
                  disabled={saving === key}
                  onValueChange={(v) => void toggle(key, v)}
                />
              </View>
            ))}
          </View>

          <Text style={styles.hint}>
            {settings.quiet_from}:00–{settings.quiet_to}:00 orasida bildirishnoma ovozsiz keladi —
            ertalab ochganingizda ko'rasiz.
          </Text>
          <Text style={styles.hint}>
            O'chirilgan toifadagi xabarlar Telegram botga avvalgidek yuboriladi — ya'ni hech qanday
            xabar yo'qolmaydi.
          </Text>
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { paddingBottom: 32, gap: 16 },
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
  // Sarlavha markazda qolishi uchun o'ng tomonda «Orqaga» kengligicha bo'shliq
  barSpacer: { width: 64 },
  center: { padding: 32, alignItems: "center" },
  card: {
    marginHorizontal: 16,
    backgroundColor: "#fff",
    borderRadius: 16,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: "#e2e8f0",
    paddingHorizontal: 16,
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
    paddingVertical: 14,
  },
  rowBorder: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: "#f1f5f9" },
  // flexShrink — uzun nom switch'ni ekrandan chiqarib yubormasin
  rowLabel: { flexShrink: 1, fontSize: 15 },
  hint: { marginHorizontal: 16, fontSize: 13, color: "#64748b", lineHeight: 18 },
  warn: {
    marginHorizontal: 16,
    backgroundColor: "#fef3c7",
    borderRadius: 12,
    padding: 12,
  },
  warnText: { fontSize: 13, color: "#92400e", lineHeight: 18 },
});
