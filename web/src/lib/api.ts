// lib/api — uch qismga bo'lingan: client (fetch), types (interfeyslar),
// endpoints (api obyekti). Eski `../lib/api` importlari buzilmasligi uchun
// hammasi shu yerdan re-export qilinadi.
export * from "./api/client";
export * from "./api/types";
export { api } from "./api/endpoints";
