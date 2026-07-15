import path from "node:path";
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import basicSsl from "@vitejs/plugin-basic-ssl";

// verifix (hodim_crm) yagona backendga birlashtirildi: davomat endi asosiy
// ilovaning "/check-in" sahifasida. Eski /verifix havolalari shu yerga
// yo'naltiriladi — ma'lumot ikki bazaga bo'linib ketmasligi uchun eski Next.js
// ilovasi endi ishlatilmaydi.
function verifixRedirect(): Plugin {
  return {
    name: "verifix-redirect",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = (req.url || "").split("?")[0];
        if (url === "/verifix" || url.startsWith("/verifix/")) {
          res.statusCode = 302;
          res.setHeader("Location", "/check-in");
          res.end();
          return;
        }
        // Eski /admin (verifix Django admin) — endi boshqaruv asosiy panelda
        // (Davomat/Ofislar sahifalari). Django bazasi eskirgan, unga yozish
        // ma'lumotni ikkiga bo'lardi.
        if (url === "/admin" || url.startsWith("/admin/")) {
          res.statusCode = 302;
          res.setHeader("Location", "/attendance");
          res.end();
          return;
        }
        next();
      });
    },
  };
}

// HTTPS portiga oddiy http:// so'rov kelsa (brauzerga "localhost:5173" deb
// yozilganda http bilan ochiladi) bo'sh javob o'rniga https'ga yo'naltiramiz.
// TCP ulanishning birinchi bayti 0x16 bo'lsa — TLS handshake (https), aks holda
// oddiy matnli HTTP — o'sha zahoti 301 redirect yozib yuboramiz.
function httpToHttpsRedirect(): Plugin {
  return {
    name: "http-to-https-redirect",
    configureServer(server) {
      const httpServer = server.httpServer;
      if (!httpServer) return;
      const tlsListeners = httpServer.listeners("connection").slice() as ((...args: unknown[]) => void)[];
      httpServer.removeAllListeners("connection");
      httpServer.on("connection", (socket: import("net").Socket) => {
        // Klient ulanishni to'satdan uzsa (ECONNRESET) jarayon qulamasin —
        // handler'siz socket xatosi Node'da "unhandled error" bo'lib butun
        // serverni o'ldiradi.
        socket.on("error", () => socket.destroy());
        socket.once("data", (chunk: Buffer) => {
          socket.pause();
          socket.unshift(chunk);
          if (chunk[0] === 0x16) {
            for (const listener of tlsListeners) listener.call(httpServer, socket);
            process.nextTick(() => socket.resume());
          } else {
            const text = chunk.toString("latin1");
            const host = /^host:\s*(\S+)/im.exec(text)?.[1] ?? "localhost:5173";
            const path = /^[A-Z]+\s+(\S+)/.exec(text)?.[1] ?? "/";
            socket.end(
              `HTTP/1.1 301 Moved Permanently\r\nLocation: https://${host}${path}\r\nConnection: close\r\n\r\n`
            );
          }
        });
      });
    },
  };
}

export default defineConfig({
  // basicSsl — o'z-o'zidan imzolangan sertifikat bilan HTTPS. Telefonda kamera
  // (Face ID) va GPS faqat xavfsiz originda ishlaydi (http://192.168.137.1:5173
  // da brauzer ikkalasini bloklaydi). Telefonda birinchi ochishda sertifikat
  // ogohlantirishini "Advanced → Proceed" bilan bir marta qabul qilish kerak.
  // VITE_NO_SSL=1 — HTTPS'siz yordamchi instans (masalan avtomatik UI tekshiruvlar
  // uchun); asosiy server doim HTTPS (telefonda kamera/GPS shart).
  plugins: [
    react(),
    verifixRedirect(),
    ...(process.env.VITE_NO_SSL === "1" ? [] : [basicSsl(), httpToHttpsRedirect()]),
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    // 0.0.0.0 — boshqa qurilmalar (telefon, hotspot) ham kira olishi uchun.
    // Telefondan: https://<kompyuter-IP>:5173 (hotspotда odatda 192.168.137.1).
    host: true,
    // API bitta origin ostida (/api → FastAPI:8000). Telefonda "localhost:8000"
    // telefonning o'zini anglatib API'ga yetmasdi; proxy bilan qurilmadan
    // qat'i nazar ishlaydi va HTTPS'da mixed-content muammosi ham yo'q.
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
