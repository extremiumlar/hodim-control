import { router } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Linking,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { ApiError, appLoginPoll, appLoginStart } from "../lib/api";
import { useAuth } from "../lib/auth";

const POLL_INTERVAL_MS = 2500;

type Phase = "idle" | "waiting" | "error";

export default function Login() {
  const { signIn } = useAuth();
  const [phase, setPhase] = useState<Phase>("idle");
  const [errorText, setErrorText] = useState("");
  // Juftlik kodi — foydalanuvchi shuni botga YOZADI. Aynan shu narsa
  // "tasdiqlayotgan odam haqiqatan shu ekranni ko'ryaptimi" degan savolga
  // javob beradi: ilgari bot deep-link ochilishi bilan darhol tasdiqlardi,
  // ya'ni hujumchi o'zi yasagan havolani xodimga yuborib, uning hisobiga
  // kira olardi (bitta bosish bilan).
  const [pairingCode, setPairingCode] = useState("");
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollTimer.current) {
      clearInterval(pollTimer.current);
      pollTimer.current = null;
    }
  }, []);

  useEffect(() => stopPolling, [stopPolling]);

  const startLogin = useCallback(async () => {
    stopPolling();
    setPhase("waiting");
    setErrorText("");
    setPairingCode("");

    try {
      const { login_token, deep_link, pairing_code } = await appLoginStart();
      setPairingCode(pairing_code);
      try {
        await Linking.openURL(deep_link);
      } catch {
        setPhase("error");
        setErrorText("Telegram ilovasi topilmadi. Telegram o'rnatilganini tekshiring.");
        return;
      }

      pollTimer.current = setInterval(async () => {
        try {
          const result = await appLoginPoll(login_token);
          if (result.status === "confirmed" && result.token) {
            stopPolling();
            await signIn(result.token);
            router.replace("/home");
          } else if (result.status === "expired") {
            stopPolling();
            setPhase("error");
            setErrorText("Havola muddati o'tdi. Qaytadan urinib ko'ring.");
          }
        } catch (e) {
          stopPolling();
          setPhase("error");
          setErrorText(e instanceof ApiError ? e.message : "Server bilan aloqa uzildi.");
        }
      }, POLL_INTERVAL_MS);
    } catch (e) {
      setPhase("error");
      setErrorText(e instanceof ApiError ? e.message : "Server bilan aloqa uzildi.");
    }
  }, [signIn, stopPolling]);

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Hodimlar Tizimi</Text>
      <Text style={styles.subtitle}>
        Kirish uchun Telegram orqali tasdiqlang — botga o'tib, quyidagi kodni yozing.
      </Text>

      {phase === "waiting" ? (
        <View style={styles.waitingBox}>
          {pairingCode ? (
            <View style={styles.codeBox}>
              <Text style={styles.codeLabel}>Botga shu kodni yozing</Text>
              <Text style={styles.code}>{pairingCode}</Text>
              <Text style={styles.codeHint}>
                Kodni hech kimga aytmang — u faqat shu qurilmaga kirish uchun.
              </Text>
            </View>
          ) : null}
          <ActivityIndicator />
          <Text style={styles.waitingText}>Telegram'da tasdiqlashingiz kutilmoqda…</Text>
          <Pressable onPress={startLogin} style={styles.secondaryButton}>
            <Text style={styles.secondaryButtonText}>Qaytadan urinish</Text>
          </Pressable>
        </View>
      ) : (
        <Pressable onPress={startLogin} style={styles.button}>
          <Text style={styles.buttonText}>Telegram orqali kirish</Text>
        </Pressable>
      )}

      {phase === "error" && <Text style={styles.error}>{errorText}</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
    padding: 24,
    gap: 16,
  },
  title: { fontSize: 28, fontWeight: "700" },
  subtitle: { fontSize: 15, textAlign: "center", color: "#555" },
  button: {
    backgroundColor: "#2563eb",
    paddingHorizontal: 24,
    paddingVertical: 14,
    borderRadius: 12,
  },
  buttonText: { color: "#fff", fontSize: 16, fontWeight: "600" },
  waitingBox: { alignItems: "center", gap: 12 },
  codeBox: {
    alignItems: "center",
    gap: 6,
    paddingHorizontal: 28,
    paddingVertical: 18,
    borderRadius: 16,
    backgroundColor: "#eff6ff",
    borderWidth: 1,
    borderColor: "#bfdbfe",
  },
  codeLabel: { fontSize: 13, color: "#1e40af", fontWeight: "600" },
  // letterSpacing — raqamlar aniq ajralib tursin, xato o'qilmasin
  code: { fontSize: 40, fontWeight: "700", letterSpacing: 8, color: "#1e3a8a" },
  codeHint: { fontSize: 12, color: "#64748b", textAlign: "center", maxWidth: 260 },
  waitingText: { color: "#555" },
  secondaryButton: { paddingHorizontal: 16, paddingVertical: 8 },
  secondaryButtonText: { color: "#2563eb", fontSize: 14 },
  error: { color: "#dc2626", textAlign: "center" },
});
