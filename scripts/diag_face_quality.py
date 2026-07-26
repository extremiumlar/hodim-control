"""Face ID deskriptorlarini chuqur tahlil — nima uchun turli odamlar bir-biriga o'xshaydi?"""
import itertools
import json
import math
import sqlite3

DB = "D:/Project/hodimlar_tizimi/app.db"
c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row

users = c.execute(
    "select full_name, face_descriptor from users where face_descriptor is not null"
).fetchall()
D = {u["full_name"].strip(): json.loads(u["face_descriptor"]) for u in users}


def dist(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


print("=" * 72)
print("FACE ID DESKRIPTOR TAHLILI")
print("=" * 72)
print()
print("face-api.js standarti: bir xil odam ~0.3-0.5, TURLI odamlar ~0.6-1.2 masofa")
print("Bu tizimda chegara: similarity >= 0.5, ya'ni masofa <= 0.5 -> 'bir xil odam'")
print()

print("--- TURLI odamlar orasidagi haqiqiy masofa ---")
pairs = []
for (n1, d1), (n2, d2) in itertools.combinations(D.items(), 2):
    dd = dist(d1, d2)
    pairs.append(dd)
    verdict = "!!! TIZIM 'BIR XIL ODAM' DEB QABUL QILADI" if dd <= 0.5 else "ok (rad etiladi)"
    print(f"  {n1:12} <-> {n2:12}: masofa={dd:.3f}  sim={max(0,1-dd):.3f}  {verdict}")

print()
print(f"  O'rtacha masofa: {sum(pairs)/len(pairs):.3f}")
print(f"  Eng kichik:      {min(pairs):.3f}   (normal: 0.6+)")
print(f"  Eng katta:       {max(pairs):.3f}")

print()
print("--- SABAB TAHLILI: deskriptorlar 'markazga' siqilganmi? ---")
dim = len(next(iter(D.values())))
centroid = [sum(d[i] for d in D.values()) / len(D) for i in range(dim)]
print(f"  Har bir deskriptorning umumiy markazdan masofasi:")
for n, d in D.items():
    print(f"     {n:12}: {dist(d, centroid):.3f}")
print()
print("  Izoh: agar bu masofalar kichik (<0.3) bo'lsa — deskriptorlar markazga")
print("  siqilgan, ya'ni ular bir-biridan deyarli farq qilmaydi.")

print()
print("--- Deskriptor statistikasi (normal face-api qiymatlari bilan solishtirish) ---")
for n, d in D.items():
    mean = sum(d) / len(d)
    var = sum((x - mean) ** 2 for x in d) / len(d)
    std = math.sqrt(var)
    l2 = math.sqrt(sum(x * x for x in d))
    print(f"  {n:12}: L2={l2:.3f}  std={std:.4f}  min={min(d):+.3f}  max={max(d):+.3f}")
print()
print("  Normal face-api deskriptori: L2 ~ 1.0, std ~ 0.09, qiymatlar -0.3..+0.3")
print("  std sezilarli KICHIK bo'lsa — o'rtachalash deskriptorni tekislagan.")

print()
print("=" * 72)
print("XULOSA")
print("=" * 72)
min_d = min(pairs)
if min_d <= 0.5:
    n_bad = sum(1 for p in pairs if p <= 0.5)
    print(f"  KRITIK: {n_bad}/{len(pairs)} juftlik chegaradan o'tadi.")
    print("  Ya'ni bu odamlar BIR-BIRINING hisobiga check-in qila oladi.")
    print("  Face ID amalda hech kimni ajratmayapti.")
else:
    print("  Deskriptorlar bir-biridan yetarlicha farq qiladi.")
c.close()
