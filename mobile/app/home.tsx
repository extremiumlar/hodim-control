import { Redirect, router } from "expo-router";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { useAuth } from "../lib/auth";
import { unregisterPush } from "../lib/push";
import { visibleSections } from "../lib/sections";

const ROLE_NAMES: Record<string, string> = {
  employee: "Xodim",
  hr: "HR",
  rop: "ROP",
  boss: "Boshliq",
  dasturchi: "Dasturchi",
};

function greeting(): string {
  const h = new Date().getHours();
  if (h < 5) return "Xayrli tun";
  if (h < 12) return "Xayrli tong";
  if (h < 18) return "Xayrli kun";
  return "Xayrli kech";
}

export default function Home() {
  const { user, signOut } = useAuth();

  if (!user) return <Redirect href="/login" />;

  // Ko'rinish shartlari `lib/sections.ts` da — bot va sayt bilan bir xil.
  const tiles = visibleSections(user);

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <View style={styles.header}>
        <Text style={styles.greeting}>
          {greeting()}, {user.full_name}!
        </Text>
        <Text style={styles.role}>
          {ROLE_NAMES[user.role] ?? user.role}
          {user.position?.name ? ` · ${user.position.name}` : ""}
        </Text>
      </View>

      <View style={styles.grid}>
        {tiles.map((tile) => (
          <Pressable
            key={tile.key}
            onPress={() =>
              tile.nativeRoute
                ? router.push(tile.nativeRoute as never)
                : // Kabinet bo'limi — saytning sahifasi WebView'da
                  router.push({
                    pathname: "/view",
                    params: { path: tile.webPath, title: tile.title },
                  } as never)
            }
            style={styles.tile}
          >
            <Text style={styles.tileEmoji}>{tile.emoji}</Text>
            <Text style={styles.tileTitle}>{tile.title}</Text>
          </Pressable>
        ))}
      </View>

      <Pressable onPress={() => router.push("/notifications" as never)} style={styles.settingsRow}>
        <Text style={styles.settingsText}>🔔 Bildirishnoma sozlamalari</Text>
      </Pressable>

      <Pressable
        onPress={async () => {
          // Avval tokenni o'chiramiz — chiqqandan keyin bu qurilmaga push
          // ketmasin (token o'chirish avtorizatsiya talab qiladi, shuning
          // uchun signOut'dan OLDIN).
          await unregisterPush();
          await signOut();
          router.replace("/login");
        }}
        style={styles.logout}
      >
        <Text style={styles.logoutText}>Chiqish</Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 20, paddingTop: 64, gap: 20 },
  header: { gap: 4 },
  greeting: { fontSize: 22, fontWeight: "700" },
  role: { fontSize: 14, color: "#555" },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 12 },
  tile: {
    width: "47%",
    backgroundColor: "#f1f5f9",
    borderRadius: 16,
    padding: 16,
    gap: 8,
  },
  tileEmoji: { fontSize: 28 },
  tileTitle: { fontSize: 14, fontWeight: "600" },
  settingsRow: {
    alignSelf: "center",
    paddingVertical: 12,
    paddingHorizontal: 16,
  },
  settingsText: { fontSize: 15, color: "#334155" },
  logout: { alignSelf: "center", padding: 12 },
  logoutText: { color: "#dc2626", fontSize: 15 },
});
