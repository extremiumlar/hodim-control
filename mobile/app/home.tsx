import { Redirect, router } from "expo-router";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { useAuth } from "../lib/auth";

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

// Bosh ekran taylari — Position.menu_flags asosida filtrlash MOBIL_ILOVA_REJASI.md
// 4.4-band: flag false bo'lsa tayl umuman ko'rinmaydi. Davomat va bilim bazasi
// flagga bog'liq emas (hammada bor).
interface Tile {
  key: string;
  title: string;
  emoji: string;
  flagKey?: string;
  /** Ekran yozilgan bo'lsa — expo-router yo'li. Bo'lmasa tayl "tez orada". */
  route?: string;
}

const TILES: Tile[] = [
  { key: "attendance", title: "Davomat (Keldim/Ketdim)", emoji: "🕐", route: "/checkin" },
  { key: "schedule", title: "Ish jadvali", emoji: "🗓" },
  { key: "tasks", title: "Vazifalarim", emoji: "📋", flagKey: "tasks" },
  { key: "norm", title: "Bugungi normam", emoji: "📊", flagKey: "norm" },
  { key: "payroll", title: "Mening oyligim", emoji: "💵", flagKey: "payroll" },
  { key: "kpi", title: "Oylik KPI'm", emoji: "💰", flagKey: "kpi" },
  { key: "knowledge", title: "Bilim bazasi", emoji: "📚" },
];

export default function Home() {
  const { user, signOut } = useAuth();

  if (!user) return <Redirect href="/login" />;

  const flags = user.position?.menu_flags ?? {};
  const tiles = TILES.filter((t) => !t.flagKey || flags[t.flagKey] !== false);

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
            disabled={!tile.route}
            onPress={tile.route ? () => router.push(tile.route as never) : undefined}
            style={[styles.tile, !tile.route && styles.tileSoon]}
          >
            <Text style={styles.tileEmoji}>{tile.emoji}</Text>
            <Text style={styles.tileTitle}>{tile.title}</Text>
            {!tile.route && <Text style={styles.tileSoonText}>Tez orada</Text>}
          </Pressable>
        ))}
      </View>

      <Pressable
        onPress={async () => {
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
  tileSoon: { opacity: 0.55 },
  tileEmoji: { fontSize: 28 },
  tileTitle: { fontSize: 14, fontWeight: "600" },
  tileSoonText: { fontSize: 11, color: "#64748b" },
  logout: { alignSelf: "center", padding: 12 },
  logoutText: { color: "#dc2626", fontSize: 15 },
});
