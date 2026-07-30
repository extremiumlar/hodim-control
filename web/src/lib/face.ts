/**
 * Face ID kutubxonasi — @vladmandic/face-api wrapper (hodim_crm/verifix'dan
 * birlashtirilgan).
 *
 * Detector: TinyFaceDetector (telefonda tez va ishonchli, ~190KB).
 * Modellar CDN'dan yuklanadi (lokal fayl kerak emas).
 *
 * Funksiyalar:
 *  - loadModels()            : barcha modellarni yuklaydi (faqat 1 marta)
 *  - captureFace(video)      : bitta freym → {descriptor, score, box}
 *  - captureLiveFace(...)    : check-in uchun: liveness + descriptor
 *  - captureForRegister(...) : ro'yxatdan o'tish uchun: eng yaxshi freym descriptori
 */
import * as faceapi from "@vladmandic/face-api";

const MODEL_URL = "https://justadudewhohacks.github.io/face-api.js/models";

// Yuz uchun minimum o'lcham (px)
export const MIN_FACE_SIZE = 60;
// Minimum freym soni ro'yxatdan o'tish uchun
export const MIN_REGISTER_FRAMES = 3;

/** Tiriklik uchun MINIMAL harakat — yuz o'lchamiga NISBATAN (0.002 = 0.2%).
 *
 * Faqat "umuman harakatsiz" (mahkam o'rnatilgan foto/ekran) holatni rad etish
 * uchun. Tirik odam nafas olishi, ko'z qisishi va beixtiyor tebranishi bilan
 * 150ms oralig'ida bundan osongina o'tadi; qo'lda ushlangan telefonda esa
 * bu qiymatdan o'n barobar yuqori chiqadi.
 *
 * Xom pikselda EMAS (ilgari `movement >= 0.5 && <= 25` shunday edi) — xom
 * piksel kamera ruxsati va masofaga bog'liq, shu sabab qurilmalar orasida
 * ko'chmaydi. YUQORI chegara ataylab YO'Q: ko'p harakat tiriklikni
 * INKOR etmaydi, balki tasdiqlaydi. */
export const MIN_MOVEMENT_RATIO = 0.002;

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
  movement: number;
  /** Harakat yuz o'lchamiga nisbatan (skala-invariant) — tiriklik qarori shunga
   * asoslanadi, xom `movement` faqat diagnostika uchun qoldirilgan. */
  movementRatio: number;
  faceSize: number;
  frames: number;
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

/** Check-in uchun: 5 freym ushlaydi, tiriklik hisoblaydi, eng yaxshi descriptorni qaytaradi. */
export async function captureLiveFace(
  video: HTMLVideoElement,
  frames: number = 5
): Promise<LiveResult | null> {
  await loadModels();
  const captures: SingleCapture[] = [];
  for (let i = 0; i < frames; i++) {
    const r = await captureFace(video);
    if (r) captures.push(r);
    await new Promise((res) => setTimeout(res, 150));
  }
  if (captures.length < 2) return null;

  const avgScore = captures.reduce((s, c) => s + c.score, 0) / captures.length;

  // Landmark harakati (pikselda) — tiriklik belgisi
  let totalMovement = 0;
  let comparisons = 0;
  for (let i = 1; i < captures.length; i++) {
    const prev = captures[i - 1].landmarks.positions;
    const cur = captures[i].landmarks.positions;
    let frameDelta = 0;
    const n = Math.min(prev.length, cur.length);
    for (let j = 0; j < n; j++) {
      frameDelta += Math.hypot(prev[j].x - cur[j].x, prev[j].y - cur[j].y);
    }
    totalMovement += frameDelta / n;
    comparisons++;
  }
  const movement = totalMovement / Math.max(1, comparisons);

  // Harakat YUZ O'LCHAMIGA nisbatan o'lchanadi (skala-invariant).
  // NEGA: `movement` xom video pikselida — u kameraning ruxsatiga va odamning
  // kameraga qanchalik yaqinligiga bog'liq. Telefonning old kamerasi (yuz 400px)
  // bilan noutbukning kamerasi (yuz 180px) bir xil real harakatda 2 barobar
  // farqli piksel beradi. Shu sabab xom pikselga qo'yilgan qat'iy chegara
  // qurilmalar orasida umuman ko'chmaydi.
  const faceSize =
    captures.reduce((s, c) => s + Math.min(c.box.w, c.box.h), 0) / captures.length;
  const movementRatio = faceSize > 0 ? movement / faceSize : 0;

  // Tiriklik: harakat MAJBURIY (statik foto/ekran rad etilishi kerak — bu
  // 71b9561 da to'g'ri aniqlangan: ilgari harakatsiz rasm 0.9 ball olardi).
  //
  // ⚠️ LEKIN yuqori chegara OLIB TASHLANDI (2026-07-27): ilgari
  // `movement >= 0.5 && movement <= 25` oynasi bor edi va undan CHIQIB
  // KETGAN harakat "tirik emas" deb baholanardi (-0.3 VA 0.3 bilan
  // cheklash — ikki marta jazo). Natijada REAL xodimlar o'ta olmadi:
  // telefonni qo'lda ushlab turgan odam 150ms oralig'ida 25 pikseldan
  // ko'p siljiydi, ayniqsa ekranda interfeys "biroz harakat qiling" deb
  // aytgani uchun. Ko'p harakat — tiriklikning KUCHLI dalili, uni rad
  // etish mantiqan ham teskari edi. Endi faqat PASTKI chegara bor.
  const hasMovement = movementRatio >= MIN_MOVEMENT_RATIO;
  let liveness = 0;
  if (captures.length >= 3) liveness += 0.2;
  if (avgScore >= 0.4) liveness += 0.2;
  if (hasMovement) liveness += 0.6;
  if (!hasMovement) liveness = Math.min(liveness, 0.3);
  liveness = Math.max(0, Math.min(1, liveness));

  const best = captures.reduce((b, c) => (c.score > b.score ? c : b));

  return {
    descriptor: best.descriptor,
    liveness,
    avgScore,
    movement,
    movementRatio,
    faceSize,
    frames: captures.length,
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
