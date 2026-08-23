"use client";

/** 后台列表页共享分页组件（页码式，对齐用户管理页样式）。 */
export default function AdminPager({
  page,
  totalPages,
  onChange,
}: {
  page: number;
  totalPages: number;
  onChange: (p: number) => void;
}) {
  if (totalPages <= 1) return null;
  const pageBtn = (active: boolean): React.CSSProperties => ({
    width: 32, height: 32, borderRadius: 4, border: "1px solid",
    borderColor: active ? "rgba(239,68,68,0.4)" : "var(--rule)",
    background: active ? "rgba(239,68,68,0.1)" : "transparent",
    color: active ? "var(--admin-red)" : "var(--muted)",
    cursor: "pointer", fontFamily: "var(--font-geist-mono), monospace", fontSize: 12,
  });
  // 页码窗口：1 … 当前±1 … N（总页数 ≤7 全显）
  const nums: Array<number | "…"> = [];
  if (totalPages <= 7) {
    for (let i = 1; i <= totalPages; i++) nums.push(i);
  } else {
    nums.push(1);
    if (page > 3) nums.push("…");
    for (let i = Math.max(2, page - 1); i <= Math.min(totalPages - 1, page + 1); i++) nums.push(i);
    if (page < totalPages - 2) nums.push("…");
    nums.push(totalPages);
  }
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8, marginTop: 16 }}>
      <button style={pageBtn(false)} disabled={page <= 1} onClick={() => onChange(page - 1)}>‹</button>
      {nums.map((n, i) =>
        n === "…" ? (
          <span key={`e${i}`} style={{ color: "var(--tertiary)", fontSize: 12, fontFamily: "var(--font-geist-mono), monospace", padding: "0 2px" }}>…</span>
        ) : (
          <button key={n} style={pageBtn(page === n)} onClick={() => onChange(n)}>{n}</button>
        )
      )}
      <button style={pageBtn(false)} disabled={page >= totalPages} onClick={() => onChange(page + 1)}>›</button>
    </div>
  );
}
