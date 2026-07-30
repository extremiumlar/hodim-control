/**
 * Face ID kutubxonasi — @vladmandic/face-api wrapper (hodim_crm/verifix'dan
 * birlashtirilgan).
 *
 * Detector: TinyFaceDetector (telefonda tez va ishonchli, ~190KB).
 * Modellar O'Z serverimizdan yuklanadi — `web/public/models/` (build'da
 * `dist/models/`, prod'da `webdist/models/`). Avval uchinchi tomon CDN'i
 * (justadudewhohacks.github.io) ishlatilardi: davomat kritik funksiya
 * bo'lgani uchun begona hostga bog'lash xatarli edi — host o'chsa yoki
 * xodim internetida bloklansa, hech kim keldim/ketdim qila olmaydi.
 *
 * Funksiyalar:
 *  - loadModels()            : barcha modellarni yuklaydi (faqat 1 marta)
 *  - captureFace(video)      : bitta freym → {descriptor, score, box}
 *  - captureLiveFace(...)    : check-in uchun: liveness + descriptor
 *  - captureForRegister(...) : ro'yxatdan o'tish uchun: eng yaxshi freym descriptori
 */
import * as faceapi from "@vladmandic/face-api";

// Nisbiy yo'l — dev'da vite public/ dan, prod'da Passenger webdist/ dan beradi.
// Mobil ilova ham shu sahifani WebView'da ochadi, ya'ni u ham shu yerdan oladi.
const MODEL_URL = "/models";

// Yuz uchun minimum o'lcham (px)
export const MIN_FACE_SIZE = 60;
// Minimum freym soni ro'yxatdan o'tish uchun
export const MIN_REGISTER_FRAMES = 3;

// ─────────────────────────────────────────────────────────────────────────
// TIRIKLIK (liveness) — HARAKAT EMAS, MIMIKA asosida.
//
// ⚠️ NEGA HARAKAT ISHLAMAYDI (2026-07-30, jonli isbot): harakatga asoslangan
// har qanday chegara printsipial ravishda aldanadi — QO'LDA USHLANGAN RASM
// ham harakatlanadi. Ikki urinish ham muvaffaqiyatsiz bo'ldi:
//   1) 71b9561: `movement 0.5..25px` oynasi → REAL xodimlar o'tolmadi
//      (telefon qo'lda 25px dan oshadi).
//   2) 4062859: yuz o'lchamiga nisbatan, yuqori chegarasiz → RASM o'tib
//      ketdi (rasmni qo'lda ushlab tursa harakat bor).
// Xulosa: o'rtacha landmark siljishi tirik yuz bilan qimirlayotgan rasmni
// ajratib BERMAYDI — ikkalasi ham "qattiq jism siljishi".
//
// YECHIM: NOQATTIQ (non-rigid) deformatsiya — rasm buni TAKRORLAY OLMAYDI:
//   • ko'z pirpiratish (EAR — Eye Aspect Ratio keskin tushadi va qaytadi)
//   • og'iz ochish (MAR — Mouth Aspect Ratio keskin oshadi)
// Rasmni xohlagancha qimirlatish/burash mumkin, lekin ko'zi yumilmaydi va
// og'zi ochilmaydi. Ikkalasidan BIRI kifoya — shu sabab real odam uchun
// oson (buyruq bilan pirpiratish yoki og'iz ochish — bir soniyalik ish).
// ─────────────────────────────────────────────────────────────────────────

// ⚙️ Chegaralar TAXMIN emas, SINTETIK 3D YUZ PROYEKSIYASI bilan o'lchab
// tanlangan (2026-07-30). Usul: tirik yuz = chuqurlikli 3D model (pirpiratish/
// og'iz ochish + tabiiy bosh harakati), rasm = TEKIS (z=0) model, unga har xil
// burash/egish/masshtab + landmark shovqini qo'llanadi. O'lchangan natija
// (shovqin ≤2px, yuz ~300px):
//   earDip     — tirik: 0.09-0.35   |  rasm (70° egilganda ham): 0.78-0.95
//   mouthDelta — tirik: 0.52+       |  rasm: 0.10-0.28
// Shu ajratishda noto'g'ri qabul 0/1500, noto'g'ri rad 0/1000 chiqdi.

/** Ko'z yumilishi deb hisoblanadigan EAR tushishi: min(EAR) / ochiq-EAR.
 * O'lchov: tirik pirpiratish 0.09 (to'liq) – 0.35 (yarim), tekis rasm eng
 * xavfli holatda 0.78. 0.60 — ikki tomonga ham keng zaxira. */
export const BLINK_DIP_RATIO = 0.60;

/** Og'iz ochilishi deb hisoblanadigan MAR o'sishi (burilishga moslangan
 * masshtabda). O'lchov: tirik og'iz ochish 0.52+, tekis rasm eng xavfli
 * holatda (70° egilgan) 0.28. 0.35 — orasida. */
export const MOUTH_OPEN_DELTA = 0.35;

/** Ko'z yumilishi XOM PIKSELDA kamida shuncha qisqarishi kerak.
 *
 * NEGA: normalizatsiya (`tiltFactor`ga bo'lish) keskin burilishda KICHIK
 * songa bo'lib, shovqinni KUCHAYTIRADI — o'lchov shovqin poliga qisqaganda
 * tasodifiy "pirpiratish" chiqishi mumkin. Xom pikseldagi mutlaq chegara
 * shu mexanizmni to'g'ridan-to'g'ri to'sadi. Real pirpiratish 160px yuzda
 * ko'z ochiqligini ~10px kamaytiradi, shovqin esa ~2px. */
export const MIN_EYE_CLOSE_PX = 2.5;

/** Og'iz ochilishi XOM PIKSELDA kamida shuncha oshishi kerak (yuqoridagi
 * bilan bir xil sabab). Real og'iz ochish 15-30px beradi. */
export const MIN_MOUTH_OPEN_PX = 6;

/** Poza IZCHILLIGI chegarasi: `tiltFactor` mediandan shu nisbatdan ko'proq
 * farq qilgan kadrlar QARORDAN CHIQARILADI.
 *
 * NEGA: agar bir necha kadr frontal, boshqalari keskin burilgan bo'lsa,
 * statistika (p25/p75/min/max) IKKI XIL geometriyani aralashtirib, sun'iy
 * "mimika" yasaydi. Aynan shu "rasmni o'rtada egish" hujumi edi —
 * o'lchovda 38% o'tib ketardi, bu filtr bilan 0.3% ga tushdi.
 *
 * Real odamga zarari YO'Q: pirpiratish/og'iz ochish burun va ko'z
 * burchaklarini qimirlatmaydi → `tiltFactor` o'zgarmaydi → kadrlar
 * izchil qoladi (o'lchov: 9 ta tirik vaziyatda 100% o'tdi, hatto bosh
 * 35° egilgan yoki asta burilgan holatlarda ham). */
export const TILT_CONSISTENCY_TOL = 0.12;

/** Tiriklik sinovi uchun MINIMAL yuz o'lchami (px).
 *
 * NEGA: landmark shovqini pikselda deyarli o'zgarmas (~1-2px), shuning uchun
 * uning ZARARI yuz o'lchamiga bog'liq — kichik yuzda nisbiy shovqin katta
 * bo'lib, tasodifiy "pirpiratish" yasashi mumkin. O'lchov: shovqin/yuz
 * nisbati 0.007 dan oshsa rasm o'tib keta boshlaydi (jitter 3px @ yuz 300px
 * → 3.7% noto'g'ri qabul). 160px — selfie masofasida (40-60 sm) bemalol
 * yetiladigan, lekin shovqinni xavfsiz mintaqada ushlab turadigan qiymat.
 * `MIN_FACE_SIZE` (60px) faqat "yuz bormi" uchun — bu esa SIFAT chegarasi. */
export const MIN_VERIFY_FACE_SIZE = 160;

/** Bazani (odamning O'Z ko'z/og'iz shakli) aniqlash uchun minimal freym.
 * Chegaralar MUTLAQ emas, har bir odamning o'z bazasiga NISBATAN — ko'z
 * shakli, ko'zoynak, yoritish odamlar orasida juda farq qiladi. */
export const MIN_CHALLENGE_FRAMES = 6;

/** Tiriklik sinovi uchun maksimal vaqt (ms).
 *
 * Xodimga "pirpirating" deb BUYURILMAYDI — shunchaki "kameraga qarab
 * turing" deyiladi va TABIIY beixtiyor pirpiratish kutiladi. Odam
 * o'rtacha 15-20 marta/daqiqa (har 3-4s) pirpiratadi, LEKIN ekranga
 * diqqat bilan tikilganda bu tezlik pasayishi mumkin (ba'zan har 10-15s
 * gacha). Shu sabab 12s dan KENGROQ — 18s, deyarli har doim kamida bitta
 * tabiiy pirpiratishni ushlab qoladi. UI `NUDGE_AFTER_MS`dan keyin
 * yumshoq eslatma ko'rsatadi (fallback, majburiy emas). */
export const CHALLENGE_MAX_MS = 18000;

/** Shuncha vaqt (ms) tabiiy pirpiratish aniqlanmasa, UI yumshoq eslatma
 * ko'rsatadi ("ko'zingizni pirpiratib qo'ying") — passiv kutishning
 * fallback'i, boshlang'ich ko'rsatma EMAS. */
export const NUDGE_AFTER_MS = 7000;

let loadingPromise: Promise<void> | null = null;

/** Yuklangan model soni (0..3) — UI progress ko'rsatkichi uchun. */
export function loadModels(onProgress?: (loaded: number, total: number) => void): Promise<void> {
  if (loadingPromise) return loadingPromise;
  const nets = [
    faceapi.nets.tinyFaceDetector,
    faceapi.nets.faceLandmark68Net,
    faceapi.nets.faceRecognitionNet,
  ];
  let loaded = 0;
  loadingPromise = Promise.all(
    nets.map((n) =>
      n.loadFromUri(MODEL_URL).then(() => {
        loaded++;
        onProgress?.(loaded, nets.length);
      })
    )
  )
    .then(() => {
      console.log("[face] Modellar yuklandi");
      return undefined;
    })
    .catch((e) => {
      console.error("[face] Model yuklash xato:", e);
      loadingPromise = null; // qayta urinishga ruxsat
      throw e;
    });
  return loadingPromise;
}

// TinyFaceDetector — telefonda tez va ishonchli
const detectorOptions = new faceapi.TinyFaceDetectorOptions({
  inputSize: 416,
  scoreThreshold: 0.3,
});

export type SingleCapture = {
  descriptor: number[];
  score: number;
  landmarks: faceapi.FaceLandmarks68;
  box: { x: number; y: number; w: number; h: number };
};

export type LiveResult = {
  descriptor: number[];
  liveness: number;
  avgScore: number;
  faceSize: number;
  frames: number;
  /** Ko'z pirpiratish aniqlandi (rasm buni qila olmaydi). */
  blinkDetected: boolean;
  /** Og'iz ochilishi aniqlandi (rasm buni qila olmaydi). */
  mouthDetected: boolean;
  /** Diagnostika: eng chuqur ko'z yumilishi (1.0 = umuman yumilmagan). */
  earDip: number;
  /** Diagnostika: og'iz ochilish farqi (0 = umuman ochilmagan). */
  mouthDelta: number;
  /** Poza juda beqaror — izchil kadrlar yetmadi (xodimga "bir joyda turing"). */
  unstablePose: boolean;
};

/** Tiriklik sinovi davomida UI'ga real-vaqtli holat (ko'rsatma va progress). */
export type LivenessProgress = {
  elapsedMs: number;
  frames: number;
  faceDetected: boolean;
  blinkDetected: boolean;
  mouthDetected: boolean;
  earDip: number;
  mouthDelta: number;
  unstablePose: boolean;
};

export type RegisterResult = {
  descriptor: number[];
  avgScore: number;
  faceSize: number;
  frames: number;
};

export async function captureFace(video: HTMLVideoElement): Promise<SingleCapture | null> {
  await loadModels();
  if (video.readyState < 2 || video.videoWidth === 0) {
    return null;
  }
  try {
    const result = await faceapi
      .detectSingleFace(video, detectorOptions)
      .withFaceLandmarks()
      .withFaceDescriptor();
    if (!result) return null;
    const b = result.detection.box;
    return {
      descriptor: Array.from(result.descriptor),
      score: result.detection.score,
      landmarks: result.landmarks,
      box: { x: b.x, y: b.y, w: b.width, h: b.height },
    };
  } catch (e) {
    console.error("[face] detection error:", e);
    return null;
  }
}

function dist(a: { x: number; y: number }, b: { x: number; y: number }): number {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

// face-api 68-nuqtali landmark indekslari
const LEFT_EYE = [36, 37, 38, 39, 40, 41];
const RIGHT_EYE = [42, 43, 44, 45, 46, 47];
const MOUTH_INNER = { left: 60, right: 64, top: 62, bottom: 66 };
// Burun qirrasi (27→30) va ko'z burchaklari orasi (36→45) — QATTIQ (rigid)
// masofalar: ko'z yumilganda ham, og'iz ochilganda ham O'ZGARMAYDI.
const NOSE_TOP = 27;
const NOSE_TIP = 30;
const EYE_OUTER_L = 36;
const EYE_OUTER_R = 45;

/**
 * Burilish koeffitsienti = burun uzunligi / ko'zlar orasi.
 *
 * ⚠️ NEGA KERAK — RASMNI EGISH HUJUMI: tekis rasmni orqaga egsa (pitch θ),
 * proyeksiyada BARCHA vertikal masofalar cos(θ) ga qisqaradi — ko'zning
 * vertikal ochiqligi ham. Ya'ni rasmni egib turib "ko'z yumildi" degan
 * signal yasash mumkin edi (EAR ~41° da 0.75 chegaradan o'tadi). Yon
 * burilishda (yaw) esa gorizontal masofalar qisqarib, MAR sun'iy oshadi —
 * "og'iz ochildi" deb o'qilishi mumkin edi.
 *
 * Yechim: EAR/MAR shu koeffitsientga BO'LINADI. Burilishda burun ham,
 * ko'z ham bir xil qisqaradi → nisbat o'zgarmaydi. Haqiqiy pirpiratish/
 * og'iz ochishda esa burun qimirlamaydi → nisbat keskin o'zgaradi.
 * Shu tarzda mimika burilishdan ajratiladi.
 */
function tiltFactor(p: { x: number; y: number }[]): number {
  const eyeSpan = dist(p[EYE_OUTER_L], p[EYE_OUTER_R]);
  if (eyeSpan <= 0) return 0;
  return dist(p[NOSE_TOP], p[NOSE_TIP]) / eyeSpan;
}

/** Bitta ko'zning EAR (Eye Aspect Ratio) — vertikal/gorizontal nisbat.
 * Ko'z yumilganda vertikal masofa nolga tushadi → EAR keskin kamayadi. */
function eyeAspectRatio(p: { x: number; y: number }[], idx: number[]): number {
  const [p1, p2, p3, p4, p5, p6] = idx.map((i) => p[i]);
  const horizontal = dist(p1, p4);
  if (horizontal <= 0) return 0;
  return (dist(p2, p6) + dist(p3, p5)) / (2 * horizontal);
}

/** Ikki ko'zning o'rtacha EAR'i, burilishga moslangan (`tiltFactor`ga qarang). */
export function earOf(landmarks: faceapi.FaceLandmarks68): number {
  const p = landmarks.positions;
  if (p.length < 68) return 0;
  const raw = (eyeAspectRatio(p, LEFT_EYE) + eyeAspectRatio(p, RIGHT_EYE)) / 2;
  const t = tiltFactor(p);
  return t > 0 ? raw / t : raw;
}

/** MAR (Mouth Aspect Ratio) — ICHKI lab ochiqligi (tashqi lab emas: tashqi
 * kontur tabassumda ham o'zgaradi, ichki esa faqat og'iz OCHILGANDA),
 * burilishga moslangan. */
export function marOf(landmarks: faceapi.FaceLandmarks68): number {
  const p = landmarks.positions;
  if (p.length < 68) return 0;
  const horizontal = dist(p[MOUTH_INNER.left], p[MOUTH_INNER.right]);
  if (horizontal <= 0) return 0;
  const raw = dist(p[MOUTH_INNER.top], p[MOUTH_INNER.bottom]) / horizontal;
  const t = tiltFactor(p);
  return t > 0 ? raw / t : raw;
}

function percentileOf(values: number[], q: number): number {
  if (!values.length) return 0;
  const s = [...values].sort((a, b) => a - b);
  const i = Math.min(s.length - 1, Math.max(0, Math.round((s.length - 1) * q)));
  return s[i];
}

/** Bitta kadrdan olingan barcha tiriklik o'lchovlari. */
export type FrameSample = {
  /** EAR, burilishga moslangan */
  ear: number;
  /** MAR, burilishga moslangan */
  mar: number;
  /** Ko'z ochiqligi XOM pikselda (shovqin polini tekshirish uchun) */
  eyePx: number;
  /** Ichki lab oralig'i XOM pikselda */
  mouthPx: number;
  /** Poza ko'rsatkichi — izchillik filtri uchun */
  tilt: number;
};

export function sampleOf(landmarks: faceapi.FaceLandmarks68): FrameSample {
  const p = landmarks.positions;
  if (p.length < 68) return { ear: 0, mar: 0, eyePx: 0, mouthPx: 0, tilt: 0 };
  return {
    ear: earOf(landmarks),
    mar: marOf(landmarks),
    eyePx:
      (dist(p[37], p[41]) + dist(p[38], p[40]) + dist(p[43], p[47]) + dist(p[44], p[46])) / 4,
    mouthPx: dist(p[MOUTH_INNER.top], p[MOUTH_INNER.bottom]),
    tilt: tiltFactor(p),
  };
}

/**
 * Yig'ilgan kadrlardan mimika aniqlanganini baholaydi. Uch qatlamli:
 *   1. IZCHILLIK filtri — pozasi keskin farq qilgan kadrlar chiqariladi
 *      (`TILT_CONSISTENCY_TOL`), aks holda aralash geometriya sun'iy
 *      "mimika" yasaydi.
 *   2. NISBIY chegara — odamning O'Z bazasiga nisbatan (ko'z shakli,
 *      ko'zoynak, yoritish odamlar orasida juda farq qiladi).
 *   3. MUTLAQ piksel chegarasi — o'lchov shovqin polidan ustun bo'lishi
 *      shart (`MIN_EYE_CLOSE_PX` / `MIN_MOUTH_OPEN_PX`).
 */
export function evaluateChallenge(samples: FrameSample[]) {
  const medTilt = percentileOf(
    samples.map((s) => s.tilt),
    0.5
  );
  const kept =
    medTilt > 0
      ? samples.filter((s) => Math.abs(s.tilt - medTilt) / medTilt <= TILT_CONSISTENCY_TOL)
      : samples;

  // Izchil kadrlar yetmasa — qaror qabul qilmaymiz (poza juda beqaror).
  if (kept.length < MIN_CHALLENGE_FRAMES) {
    return {
      earDip: 1,
      mouthDelta: 0,
      blinkDetected: false,
      mouthDetected: false,
      unstablePose: true,
    };
  }

  const openEar = percentileOf(kept.map((s) => s.ear), 0.75); // "ochiq ko'z" bazasi
  const minEar = Math.min(...kept.map((s) => s.ear));
  const earDip = openEar > 0 ? minEar / openEar : 1;
  const eyeDropPx = percentileOf(kept.map((s) => s.eyePx), 0.75) - Math.min(...kept.map((s) => s.eyePx));

  const closedMar = percentileOf(kept.map((s) => s.mar), 0.25); // "yopiq og'iz" bazasi
  const mouthDelta = Math.max(...kept.map((s) => s.mar)) - closedMar;
  const mouthRisePx =
    Math.max(...kept.map((s) => s.mouthPx)) - percentileOf(kept.map((s) => s.mouthPx), 0.25);

  return {
    earDip,
    mouthDelta,
    blinkDetected: earDip <= BLINK_DIP_RATIO && eyeDropPx >= MIN_EYE_CLOSE_PX,
    mouthDetected: mouthDelta >= MOUTH_OPEN_DELTA && mouthRisePx >= MIN_MOUTH_OPEN_PX,
    unstablePose: false,
  };
}

/**
 * Check-in uchun tiriklik sinovi — MIMIKA asosida (harakat EMAS, yuqoridagi
 * uzun izohga qarang).
 *
 * Kadrlarni to'xtovsiz o'qiydi va har biridan EAR/MAR hisoblaydi. Ko'z
 * pirpiratish YOKI og'iz ochilishi aniqlangan zahoti DARHOL to'xtaydi
 * (real odam uchun bu 1-3 soniya). Ikkalasidan biri kifoya — bu ataylab
 * yumshoq: ko'zoynakli odam pirpiratishi noaniq chiqsa og'iz orqali o'tadi.
 *
 * Rasm/ekran esa ikkalasini ham qila olmaydi — qanchalik qimirlatilsa ham.
 */
export async function captureLiveFace(
  video: HTMLVideoElement,
  opts: {
    maxMs?: number;
    onProgress?: (p: LivenessProgress) => void;
    shouldCancel?: () => boolean;
  } = {}
): Promise<LiveResult | null> {
  const maxMs = opts.maxMs ?? CHALLENGE_MAX_MS;
  await loadModels();

  const started = Date.now();
  const captures: SingleCapture[] = [];
  const samples: FrameSample[] = [];
  let state = {
    earDip: 1,
    mouthDelta: 0,
    blinkDetected: false,
    mouthDetected: false,
    unstablePose: false,
  };

  while (Date.now() - started < maxMs) {
    if (opts.shouldCancel?.()) return null;

    const r = await captureFace(video);
    if (r) {
      captures.push(r);
      samples.push(sampleOf(r.landmarks));
      // Baza yig'ilmaguncha baholamaymiz — aks holda birinchi freymlarning
      // shovqini "pirpiratish" deb noto'g'ri o'qilishi mumkin.
      if (samples.length >= MIN_CHALLENGE_FRAMES) {
        state = evaluateChallenge(samples);
      }
    }

    opts.onProgress?.({
      elapsedMs: Date.now() - started,
      frames: captures.length,
      faceDetected: !!r,
      ...state,
    });

    if (state.blinkDetected || state.mouthDetected) break; // tasdiqlandi
    await new Promise((res) => setTimeout(res, 40));
  }

  if (captures.length < MIN_CHALLENGE_FRAMES) return null;

  const avgScore = captures.reduce((s, c) => s + c.score, 0) / captures.length;
  const faceSize =
    captures.reduce((s, c) => s + Math.min(c.box.w, c.box.h), 0) / captures.length;

  // Descriptor uchun ko'zi OCHIQ freymlar tanlanadi — pirpiratish paytidagi
  // (ko'z yumilgan) freymning descriptori yuzni yomon ifodalaydi va
  // solishtirishda noto'g'ri "boshqa odam" natijasini berishi mumkin.
  const openEarAll = percentileOf(samples.map((s) => s.ear), 0.75);
  const openEyed = captures.filter((_, i) => openEarAll <= 0 || samples[i].ear >= openEarAll * 0.85);
  const pool = openEyed.length ? openEyed : captures;
  const best = pool.reduce((b, c) => (c.score > b.score ? c : b));

  const challengePassed = state.blinkDetected || state.mouthDetected;
  let liveness = 0;
  if (captures.length >= MIN_CHALLENGE_FRAMES) liveness += 0.2;
  if (avgScore >= 0.4) liveness += 0.2;
  if (challengePassed) liveness += 0.6;
  // Mimika yo'q — hech qanday freym/aniqlik kombinatsiyasi buni qoplamaydi.
  if (!challengePassed) liveness = Math.min(liveness, 0.3);
  liveness = Math.max(0, Math.min(1, liveness));

  return {
    descriptor: best.descriptor,
    liveness,
    avgScore,
    faceSize,
    frames: captures.length,
    blinkDetected: state.blinkDetected,
    mouthDetected: state.mouthDetected,
    earDip: state.earDip,
    mouthDelta: state.mouthDelta,
    unstablePose: state.unstablePose,
  };
}

/** Ro'yxatdan o'tish uchun: bir nechta freym ushlaydi va ENG YAXSHISINI tanlaydi
 * (o'rtachalash 71b9561 da olib tashlangan — u barcha yuzlarni bir-biriga
 * o'xshab qolishiga olib kelgan edi). */
export async function captureForRegister(
  video: HTMLVideoElement,
  frames: number = 8
): Promise<RegisterResult | { error: string }> {
  await loadModels();
  const captures: SingleCapture[] = [];
  let attempts = 0;
  const maxAttempts = frames * 4;
  let lastSeenFaceSize = 0;
  let detectionsCount = 0;

  while (captures.length < frames && attempts < maxAttempts) {
    attempts++;
    const r = await captureFace(video);
    if (r) {
      detectionsCount++;
      const size = Math.min(r.box.w, r.box.h);
      lastSeenFaceSize = Math.max(lastSeenFaceSize, size);
      if (size >= MIN_FACE_SIZE) {
        captures.push(r);
      }
    }
    await new Promise((res) => setTimeout(res, 100));
  }

  if (captures.length < MIN_REGISTER_FRAMES) {
    let hint = "";
    if (detectionsCount === 0) {
      hint = "Yuz umuman aniqlanmadi. Yorug' joyda kameraga to'g'ri qarang.";
    } else if (lastSeenFaceSize < MIN_FACE_SIZE) {
      hint =
        `Yuz juda kichik ko'rinyapti (${lastSeenFaceSize.toFixed(0)}px, kerak ${MIN_FACE_SIZE}px). ` +
        `Kameraga yaqinroq turing.`;
    } else {
      hint = "Yuz to'liq ko'rinishi kerak (peshana, ko'z, og'iz, iyak).";
    }
    return {
      error: `Yetarli aniq freym to'planmadi (${captures.length}/${MIN_REGISTER_FRAMES}). ${hint}`,
    };
  }

  const faceSize =
    captures.reduce((s, c) => s + Math.min(c.box.w, c.box.h), 0) / captures.length;
  const avgScore = captures.reduce((s, c) => s + c.score, 0) / captures.length;

  // ENG YAXSHI freymni tanlaymiz (check-in'dagi captureLiveFace bilan bir xil usul) —
  // ILGARI bu yerda descriptorlar element-wise O'RTACHALANARDI, bu esa shaxsiy
  // xususiyatlarni yo'qotib barcha ro'yxatdan o'tgan yuzlarni "o'rtacha yuz"ga
  // siljitardi (jonli isbot: 4 ta ro'yxatdan o'tgan yuzning HAMMASI bir-biriga
  // 0.5 chegaradan yaqin chiqdi — tizim turli odamlarni bitta odam deb qabul
  // qilardi). Eng yaxshi (aniqlik balli eng yuqori) freymning haqiqiy descriptori
  // saqlanadi — o'rtachalash yo'q.
  const best = captures.reduce((b, c) => (c.score > b.score ? c : b));

  return { descriptor: best.descriptor, avgScore, faceSize, frames: captures.length };
}
