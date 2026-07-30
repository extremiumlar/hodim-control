"""Brend ikonkalarini "logo 1.png" dan generatsiya qiladi.

Ishlatish (loyiha ildizidan):
    python scripts/make_icons.py

NEGA SKRIPT: `expo prebuild` ikonkalarni o'zi yasay oladi, LEKIN u
`mobile/android/` ni butunlay qayta yaratadi va release imzo sozlamalari,
CMake staging yo'li (Windows MAX_PATH) hamda kamera/GPS ruxsatlari
yo'qoladi (MOBIL_ILOVA_REJASI.md 8.5). Shuning uchun Android resurslarini
shu skript to'g'ridan-to'g'ri yozadi.

NEGA BELGI KESIB OLINADI: to'liq logoda "NURIDDIN BUILDINGS" yozuvi bor —
48-72 px launcher ikonkasida u o'qilmas chiziqqa aylanadi. Ikonka uchun
faqat tilla "N" belgisi ishlatiladi, to'liq logo esa splash ekranida
(katta o'lchamda o'qiladi).
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "logo 1.png"

# Logo foni — bir tekis to'q yashil. Alfa niqobi shu rangdan uzoqlik
# bo'yicha hisoblanadi, shuning uchun aniq qiymat muhim.
BG = (0, 43, 41)
BG_HEX = "#002B29"

# Tilla "N" belgisining chegarasi (skript bilan o'lchangan: 700x884 px,
# gorizontal markazda). Logo fayli o'zgarsa QAYTA O'LCHANISHI kerak —
# quyidagi _measure_mark() yordamchisi shuni chiqaradi.
MARK_BOX = (1420, 956, 2120, 1840)


def _measure_mark(im: Image.Image) -> tuple[int, int, int, int]:
    """Tilla piksellar chegarasini topadi (MARK_BOX ni tekshirish uchun)."""
    px = im.load()
    w, h = im.size
    x0, y0, x1, y1 = w, h, 0, 0
    for y in range(0, h, 4):
        for x in range(0, w, 4):
            r, g, b = px[x, y]
            if r > 120 and b < r * 0.75 and not (r > 240 and g > 240 and b > 240):
                x0, y0 = min(x0, x), min(y0, y)
                x1, y1 = max(x1, x), max(y1, y)
    return x0, y0, x1, y1


def mark_rgba() -> Image.Image:
    """Tilla "N" belgisi, foni shaffof (chetlari yumshoq qoladi)."""
    logo = Image.open(SRC).convert("RGB")
    crop = logo.crop(MARK_BOX)

    # Bir tekis fon ustidagi shaklni ajratish: har piksel fon rangidan
    # qancha farq qilsa, shuncha ko'p ko'rinadi. Kanallar bo'yicha MAKSIMUM
    # farqni olamiz (L ga o'tkazish yorqinlik bo'yicha o'rtalashtirib,
    # tilla rangning ko'k kanalini yo'qotardi).
    solid = Image.new("RGB", crop.size, BG)
    diff = ImageChops.difference(crop, solid)
    r, g, b = diff.split()
    mask = ImageChops.lighter(ImageChops.lighter(r, g), b)

    # Eng yorqin nuqtani 255 ga keltirib normallashtiramiz, aks holda
    # belgi yarim shaffof bo'lib qoladi.
    peak = mask.getextrema()[1] or 255
    mask = mask.point(lambda v: min(255, v * 255 // peak))

    out = crop.convert("RGBA")
    out.putalpha(mask)
    return out


def _fit(mark: Image.Image, canvas: int, frac: float) -> Image.Image:
    """Belgini `canvas` o'lchamli shaffof kvadrat markaziga joylashtiradi.

    `frac` — belgi balandligi kanvasning qancha ulushini egallasin.
    Adaptive ikonkada xavfsiz soha 108dp dan 66dp (~0.61) — foreground
    qatlamda shundan oshmasligi kerak, aks holda doira niqobda kesiladi.
    """
    target_h = max(1, int(canvas * frac))
    scale = target_h / mark.height
    size = (max(1, round(mark.width * scale)), target_h)
    resized = mark.resize(size, Image.LANCZOS)

    layer = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    layer.paste(resized, ((canvas - size[0]) // 2, (canvas - size[1]) // 2), resized)
    return layer


def solid(canvas: int) -> Image.Image:
    return Image.new("RGBA", (canvas, canvas), BG + (255,))


def icon(canvas: int, frac: float = 0.58) -> Image.Image:
    """To'liq ikonka: to'q yashil fon + markazda tilla belgi."""
    base = solid(canvas)
    base.alpha_composite(_fit(mark_rgba(), canvas, frac))
    return base


def foreground(canvas: int, frac: float = 0.52) -> Image.Image:
    """Adaptive ikonka foreground qatlami — shaffof fonda belgi."""
    return _fit(mark_rgba(), canvas, frac)


def monochrome(canvas: int, frac: float = 0.52) -> Image.Image:
    """Themed icons uchun: belgi siluetini oq rangda beradi."""
    layer = _fit(mark_rgba(), canvas, frac)
    white = Image.new("RGBA", layer.size, (255, 255, 255, 255))
    white.putalpha(layer.getchannel("A"))
    return white


def full_logo(canvas: int) -> Image.Image:
    """To'liq logo (yozuvi bilan) — splash uchun, O'Z foni bilan.

    Fonni shaffof qilmaymiz: splash fon rangi ham aynan BG, ya'ni chok
    ko'rinmaydi. Shaffof qilishga urinish alfa aniqligini buzardi — oq
    yozuv fondan eng uzoq piksel bo'lib normallashtirish bazasi bo'lib
    qolar va tilla rang ~80% shaffoflikda xiralashardi.
    """
    logo = Image.open(SRC).convert("RGBA")
    return logo.resize((canvas, canvas), Image.LANCZOS)


def save(im: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)
    print(f"  {path.relative_to(ROOT)}  {im.size[0]}x{im.size[1]}")


def main() -> None:
    logo = Image.open(SRC).convert("RGB")
    measured = _measure_mark(logo)
    if measured != MARK_BOX:
        print(f"DIQQAT: belgi chegarasi o'zgargan — o'lchandi {measured}, "
              f"MARK_BOX {MARK_BOX}. Skriptdagi qiymatni yangilang.")

    # ── Expo manba assetlari (prebuild qayta ishlatilsa shular olinadi) ──
    print("mobile/assets:")
    m = ROOT / "mobile" / "assets"
    save(icon(1024), m / "icon.png")
    save(foreground(1024), m / "android-icon-foreground.png")
    save(solid(1024), m / "android-icon-background.png")
    save(monochrome(1024), m / "android-icon-monochrome.png")
    save(full_logo(1024), m / "splash-icon.png")
    save(icon(48), m / "favicon.png")

    # ── Android resurslari (prebuild ishlatilmaydi — qo'lda yoziladi) ──
    # Launcher: 48dp (mdpi 1x). Adaptive qatlamlar: 108dp.
    print("android res (mipmap):")
    res = ROOT / "mobile" / "android" / "app" / "src" / "main" / "res"
    densities = {"mdpi": 1, "hdpi": 1.5, "xhdpi": 2, "xxhdpi": 3, "xxxhdpi": 4}
    for name, mult in densities.items():
        legacy = int(48 * mult)
        adaptive = int(108 * mult)
        d = res / f"mipmap-{name}"
        save(icon(legacy), d / "ic_launcher.webp")
        save(icon(legacy), d / "ic_launcher_round.webp")
        save(solid(adaptive), d / "ic_launcher_background.webp")
        save(foreground(adaptive), d / "ic_launcher_foreground.webp")
        save(monochrome(adaptive), d / "ic_launcher_monochrome.webp")

    print("android res (splash):")
    for name, side in {"mdpi": 288, "hdpi": 432, "xhdpi": 576,
                       "xxhdpi": 864, "xxxhdpi": 1152}.items():
        save(full_logo(side), res / f"drawable-{name}" / "splashscreen_logo.png")

    # ── Web PWA ──
    print("web/public (PWA):")
    p = ROOT / "web" / "public"
    save(icon(192), p / "icon-192.png")
    save(icon(512), p / "icon-512.png")
    # maskable: Android/Chrome ikonkani kesadi — belgi kichikroq bo'lsin.
    save(icon(512, frac=0.44), p / "icon-maskable-512.png")
    # iOS bosh ekran ikonkasi — Apple o'zi burchaklarni yumaloqlaydi,
    # shuning uchun fon to'liq bo'lishi kerak (shaffof bo'lsa qora chiqadi).
    save(icon(180), p / "apple-touch-icon.png")
    save(icon(48), p / "favicon.png")

    print(f"\nTayyor. Fon rangi: {BG_HEX}")


if __name__ == "__main__":
    main()
