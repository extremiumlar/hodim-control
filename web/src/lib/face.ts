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
 *  - captureForRegister(...) : ro'yxatdan o'tish uchun: bir nechta freym o'rtachasi
 */
import * as faceapi from "@vladmandic/face-api";

const MODEL_URL = "https://justadudewhohacks.github.io/face-api.js/models";

// Yuz uchun minimum o'lcham (px)
export const MIN_FACE_SIZE = 60;
// Minimum freym soni ro'yxatdan o'tish uchun
export const MIN_REGISTER_FRAMES = 3;

let loadingPromise: Promise<void> | null = null;

export async function loadModels(): Promise<void> {
  if (loadingPromise) return loadingPromise;
  loadingPromise = Promise.all([
    faceapi.nets.tinyFaceDetector.loadFromUri(MODEL_URL),
    faceapi.nets.faceLandmark68Net.loadFromUri(MODEL_URL),
    faceapi.nets.faceRecognitionNet.loadFromUri(MODEL_URL),
  ])
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

  // Tiriklik formulasi (hodim_crm bilan bir xil)
  let liveness = 0.4;
  if (captures.length >= 3) liveness += 0.25;
  if (avgScore >= 0.4) liveness += 0.25;
  if (movement >= 0.5 && movement <= 25) liveness += 0.2;
  if (movement > 25) liveness -= 0.2;
  liveness = Math.max(0, Math.min(1, liveness));

  const best = captures.reduce((b, c) => (c.score > b.score ? c : b));

  return {
    descriptor: best.descriptor,
    liveness,
    avgScore,
    movement,
    frames: captures.length,
  };
}

/** Ro'yxatdan o'tish uchun: bir nechta freym ushlaydi va descriptorlarni O'RTACHALAYDI. */
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

  // Descriptorlarni o'rtachalash (element-wise mean) — L2 normalizatsiya QILMAYMIZ:
  // check-in descriptorlari ham normalizatsiyasiz, masshtab bir xil bo'lishi kerak.
  const dim = captures[0].descriptor.length;
  const avgDescriptor = new Array(dim).fill(0);
  for (const c of captures) {
    for (let i = 0; i < dim; i++) avgDescriptor[i] += c.descriptor[i];
  }
  for (let i = 0; i < dim; i++) avgDescriptor[i] /= captures.length;

  return { descriptor: avgDescriptor, avgScore, faceSize, frames: captures.length };
}
