import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import { Nunito, Patrick_Hand } from "next/font/google";
import "./globals.css";

const nunito = Nunito({
  variable: "--font-nunito",
  subsets: ["latin"],
  display: "swap",
});

const patrickHand = Patrick_Hand({
  variable: "--font-patrick-hand",
  subsets: ["latin"],
  weight: "400",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "Plus11 — a little practice, a lot of progress",
    template: "%s | Plus11",
  },
  description: "A calm place to practise, learn, and see your progress.",
  icons: { icon: "/plus11-mark.svg" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#FBFAF6",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en" className={`${nunito.variable} ${patrickHand.variable}`}>
      <body>{children}</body>
    </html>
  );
}
