import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // hodim_crm (verifix) ni bitta manzil ostida ko'rsatish uchun dev-proxy:
    //   localhost:5173/         -> hodimlar_tizimi (shu Vite ilovasi)
    //   localhost:5173/verifix  -> verifix Next.js (:3000, basePath=/verifix)
    // Ishlab chiqarishda buni nginx qiladi (deploy/nginx-gateway.conf).
    proxy: {
      "/verifix": {
        target: "http://localhost:3000",
        changeOrigin: true,
        ws: true, // Next.js HMR/WebSocket
      },
    },
  },
});
