import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";

import PushGate from "../components/PushGate";
import { AuthProvider } from "../lib/auth";

const queryClient = new QueryClient();

export default function RootLayout() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <StatusBar style="auto" />
        {/* Hech narsa render qilmaydi — push tokeni va bildirishnoma
            bosilishini kuzatadi (AuthProvider ICHIDA bo'lishi shart). */}
        <PushGate />
        <Stack screenOptions={{ headerShown: false }} />
      </AuthProvider>
    </QueryClientProvider>
  );
}
