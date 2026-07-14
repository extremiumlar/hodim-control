import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // 0.0.0.0 — boshqa qurilmalar (telefon, hotspot) ham kira olishi uchun.
    // Telefondan: http://<kompyuter-IP>:5173 (hotspotда odatda 192.168.137.1).
    host: true,
    // Bitta domen ostida:
    //   /         -> hodimlar_tizimi (shu Vite ilovasi)
    //   /verifix  -> verifix Next.js (:3000, basePath=/verifix)
    //   /admin    -> verifix Django backend admin paneli (:8002)
    //   /static   -> Django admin CSS/JS (runserver DEBUG'da beradi)
    // Ishlab chiqarishда buni nginx qiladi (deploy/nginx-gateway.conf).
    // DIQQAT: /admin va /static uchun changeOrigin YO'Q — Host sarlavhasi
    // saqlanadi, shunda Django CSRF Origin==Host tekshiruvi o'tadi.
    proxy: {
      "/verifix": {
        target: "http://localhost:3000",
        changeOrigin: true,
        ws: true, // Next.js HMR/WebSocket
      },
      "/admin": { target: "http://localhost:8002" },
      "/static": { target: "http://localhost:8002" },
    },
  },
});
