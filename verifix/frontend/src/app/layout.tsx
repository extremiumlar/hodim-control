import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Hodim CRM",
  description: "Hodimlar boshqaruvi tizimi",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="uz">
      <body>{children}</body>
    </html>
  );
}
