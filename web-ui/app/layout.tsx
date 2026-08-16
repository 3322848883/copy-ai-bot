import type { Metadata } from "next";
import type { CSSProperties } from "react";
import localFont from "next/font/local";
import "./globals.css";
import { Providers } from "@/components/Providers";
import { WsProvider } from "@/components/WsProvider";
import Nav from "@/components/Nav";

const geistSans = localFont({
  src: "./fonts/GeistVF.woff",
  variable: "--font-geist-sans",
  weight: "100 900",
});
const geistMono = localFont({
  src: "./fonts/GeistMonoVF.woff",
  variable: "--font-geist-mono",
  weight: "100 900",
});

export const metadata: Metadata = {
  title: "signal·saas 信号聚合跟单平台",
  description: "跨 5 大交易所信号聚合 + 一键跟单 SaaS",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body className={`${geistSans.variable} ${geistMono.variable}`}>
        <Providers>
          <WsProvider>
            {/* 信号宇宙背景层（全站 6 层：aurora / grid / dots / sweep / noise / particles） */}
            <div className="aurora" />
            <div className="grid-bg" />
            <div className="bg-dots" />
            <div className="bg-sweep" />
            <div className="bg-noise" />
            <div className="bg-particles">
              <i style={{ left: "6%", "--dur": "17s", "--delay": "0s", "--drift": "14px" } as CSSProperties}></i>
              <i style={{ left: "14%", "--dur": "23s", "--delay": "4s", "--drift": "-12px" } as CSSProperties}></i>
              <i style={{ left: "23%", "--dur": "19s", "--delay": "8s", "--drift": "10px" } as CSSProperties}></i>
              <i style={{ left: "32%", "--dur": "25s", "--delay": "1s", "--drift": "-16px" } as CSSProperties}></i>
              <i style={{ left: "41%", "--dur": "16s", "--delay": "6s", "--drift": "12px" } as CSSProperties}></i>
              <i style={{ left: "52%", "--dur": "21s", "--delay": "11s", "--drift": "-10px" } as CSSProperties}></i>
              <i style={{ left: "61%", "--dur": "18s", "--delay": "2s", "--drift": "16px" } as CSSProperties}></i>
              <i style={{ left: "70%", "--dur": "24s", "--delay": "9s", "--drift": "-14px" } as CSSProperties}></i>
              <i style={{ left: "79%", "--dur": "20s", "--delay": "5s", "--drift": "10px" } as CSSProperties}></i>
              <i style={{ left: "88%", "--dur": "22s", "--delay": "12s", "--drift": "-12px" } as CSSProperties}></i>
              <i style={{ left: "94%", "--dur": "17s", "--delay": "7s", "--drift": "8px" } as CSSProperties}></i>
              <i style={{ left: "10%", "--dur": "26s", "--delay": "14s", "--drift": "-8px" } as CSSProperties}></i>
            </div>
            <Nav />
            {children}
          </WsProvider>
        </Providers>
      </body>
    </html>
  );
}

