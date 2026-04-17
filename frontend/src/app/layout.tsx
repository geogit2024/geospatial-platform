import type { Metadata } from "next";
import "./globals.css";
import AppShell from "@/components/AppShell";

export const metadata: Metadata = {
  title: "GeoPublish - Plataforma de Imagens Geoespaciais",
  description: "Upload, processamento e publicacao OGC de imagens raster",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body className="bg-[#0b1220] text-gray-100 antialiased">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
