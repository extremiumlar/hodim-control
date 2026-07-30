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

    try {
      const { login_token, deep_link } = await appLoginStart();
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
        Kirish uchun Telegram orqali tasdiqlang — botga o'tib «Tasdiqlash» tugmasini bosing.
      </Text>

      {phase === "waiting" ? (
        <View style={styles.waitingBox}>
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
  waitingText: { color: "#555" },
  secondaryButton: { paddingHorizontal: 16, paddingVertical: 8 },
  secondaryButtonText: { color: "#2563eb", fontSize: 14 },
  error: { color: "#dc2626", textAlign: "center" },
});
