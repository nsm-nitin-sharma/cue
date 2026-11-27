import type { Metadata } from "next";
import { Plus_Jakarta_Sans, JetBrains_Mono, Noto_Sans_Devanagari } from "next/font/google";
import "./globals.css";
import { CueWorkspaceProvider } from "@/store/CueWorkspaceContext";

const plusJakarta = Plus_Jakarta_Sans({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const notoDevanagari = Noto_Sans_Devanagari({
  subsets: ["devanagari"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-devanagari",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Cue — Voice-First Business Operating System",
  description:
    "Run your kirana or retail business by speaking naturally in Hindi, Hinglish, or English.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${plusJakarta.variable} ${notoDevanagari.variable} ${jetbrainsMono.variable}`}
    >
      <body className="font-sans bg-paper text-ink antialiased selection:bg-vermilion-soft selection:text-ink">
        <CueWorkspaceProvider>{children}</CueWorkspaceProvider>
      </body>
    </html>
  );
}
