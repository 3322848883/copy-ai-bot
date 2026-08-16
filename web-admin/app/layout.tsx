import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";
import { ConfirmProvider } from "@/components/ConfirmDialog";
import AdminShell from "@/components/AdminShell";

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
  title: "signal·saas 运营后台",
  description: "signal-saas 信号聚合跟单平台管理后台",
};

/** 独立后台 SPA 根布局：与前台 web-ui 完全隔离，无前台 Nav/Providers/WsProvider。 */
export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body className={`${geistSans.variable} ${geistMono.variable}`}>
        <ConfirmProvider>
          <AdminShell>{children}</AdminShell>
        </ConfirmProvider>
      </body>
    </html>
  );
}