"use client";

/**
 * 迷你收益曲线 spark（对齐设计稿）：SVG 折线 + 渐变填充。
 * 默认按末值正负取色（正绿 #28c464 / 负红 #ef4444）；也可通过 color 强制指定。
 * values 为现有 roi/pnl 数据数组，不足 2 点时退化为平线。
 */
export function Sparkline({
  id,
  values,
  color,
  w = 260,
  h = 52,
}: {
  id: string;
  values: number[];
  color?: string;
  w?: number;
  h?: number;
}) {
  const PAD = 6;
  const pts = values.length >= 2 ? values : [0, 0];
  const min = Math.min(...pts);
  const max = Math.max(...pts);
  const span = Math.max(max - min, 1e-6);
  const ys = pts.map((v) => PAD + (h - 2 * PAD) * (1 - (v - min) / span));
  const xs = pts.map((_, i) => (i / (pts.length - 1)) * w);
  const d = smoothPath(xs, ys);
  const up = (pts[pts.length - 1] ?? 0) >= 0;
  const stroke = color ?? (up ? "#28c464" : "#ef4444");
  const gid = `spark-${id}`;
  const area = `${d} L${xs[xs.length - 1].toFixed(1)},${h} L${xs[0].toFixed(1)},${h} Z`;

  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="none"
      style={{ width: "100%", height: "100%", display: "block" }}
      aria-hidden
    >
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.32" />
          <stop offset="100%" stopColor={stroke} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${gid})`} />
      <path d={d} fill="none" stroke={stroke} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={xs[xs.length - 1]} cy={ys[ys.length - 1]} r="2.4" fill={stroke} />
    </svg>
  );
}

/** Catmull-Rom 平滑折线 → SVG cubic bezier path。 */
function smoothPath(xs: number[], ys: number[]): string {
  if (xs.length < 2) return "";
  let d = `M${xs[0].toFixed(1)},${ys[0].toFixed(1)}`;
  for (let i = 0; i < xs.length - 1; i++) {
    const x0 = xs[Math.max(0, i - 1)];
    const y0 = ys[Math.max(0, i - 1)];
    const x1 = xs[i];
    const y1 = ys[i];
    const x2 = xs[i + 1];
    const y2 = ys[i + 1];
    const x3 = xs[Math.min(xs.length - 1, i + 2)];
    const y3 = ys[Math.min(xs.length - 1, i + 2)];
    const c1x = x1 + (x2 - x0) / 6;
    const c1y = y1 + (y2 - y0) / 6;
    const c2x = x2 - (x3 - x1) / 6;
    const c2y = y2 - (y3 - y1) / 6;
    d += ` C${c1x.toFixed(1)},${c1y.toFixed(1)} ${c2x.toFixed(1)},${c2y.toFixed(1)} ${x2.toFixed(1)},${y2.toFixed(1)}`;
  }
  return d;
}
