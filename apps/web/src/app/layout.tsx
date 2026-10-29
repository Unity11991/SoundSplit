import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "SoundSplit — Simple AI Voice & Music Isolator",
  description:
    "Isolate clear foreground speech and background music from any audio or video file in seconds.",
  keywords: [
    "SoundSplit",
    "vocal remover",
    "speech isolation",
    "background music remover",
    "voice separator",
    "audio cleaner",
  ],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased dark`}
      suppressHydrationWarning
    >
      <body
        className="min-h-full flex flex-col bg-[#0b0d13] text-gray-100"
        suppressHydrationWarning
      >
        {children}
      </body>
    </html>
  );
}
