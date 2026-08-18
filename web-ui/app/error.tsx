"use client";

import Link from "next/link";

export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="page-wrap" style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: "60vh", textAlign: "center" }}>
      <div style={{ fontSize: 48 }}>⚠</div>
      <h1 style={{ fontSize: 20, fontWeight: 700, marginTop: 12 }}>页面出错了</h1>
      <p style={{ fontSize: 13, color: "var(--muted)", marginTop: 8, lineHeight: 1.7 }}>
        渲染过程发生异常，你的账户与持仓数据不受影响。<br />
        {error.digest && <span style={{ fontFamily: "var(--font-geist-mono)", fontSize: 11, color: "var(--tertiary)" }}>参考码：{error.digest}</span>}
      </p>
      <div style={{ display: "flex", gap: 12, marginTop: 24 }}>
        <button onClick={reset} style={{ padding: "10px 24px", fontSize: 13, fontWeight: 600, background: "var(--accent)", color: "#06281f", borderRadius: 8, border: "none", cursor: "pointer" }}>
          重试
        </button>
        <Link href="/" style={{ padding: "10px 24px", fontSize: 13, border: "1px solid var(--rule)", color: "var(--muted)", borderRadius: 8, textDecoration: "none" }}>
          返回首页
        </Link>
      </div>
    </div>
  );
}
