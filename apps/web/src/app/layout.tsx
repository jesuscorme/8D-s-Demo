import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = { title: "8D PRO", description: "Gestión de casos 8D" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}
