import Link from "next/link";

export default function NotFound() {
  return (
    <div className="page-wrap" style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: "60vh", textAlign: "center" }}>
      <div style={{ fontSize: 72, fontWeight: 800, fontFamily: "var(--font-geist-mono)", color: "var(--accent)", letterSpacing: "-0.04em" }}>404</div>
      <h1 style={{ fontSize: 20, fontWeight: 700, marginTop: 8 }}>页面未找到</h1>
      <p style={{ fontSize: 13, color: "var(--muted)", marginTop: 8, lineHeight: 1.7 }}>
        你访问的页面不存在或已被移动。<br />Alpha 引擎仍在运转，回到主线继续。
      </p>
      <div style={{ display: "flex", gap: 12, marginTop: 24 }}>
        <Link href="/" style={{ padding: "10px 24px", fontSize: 13, fontWeight: 600, background: "var(--accent)", color: "#06281f", borderRadius: 8, textDecoration: "none" }}>
          返回首页
        </Link>
        <Link href="/strategies" style={{ padding: "10px 24px", fontSize: 13, border: "1px solid var(--rule)", color: "var(--muted)", borderRadius: 8, textDecoration: "none" }}>
          浏览策略广场
        </Link>
      </div>
    </div>
  );
}
