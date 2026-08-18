"use client";

import { useId } from "react";

/** OmniAlpha 品牌视觉：六边形（信号聚合）内嵌 Ω（全知/Alpha），teal→cyan 渐变。 */

export function BrandMark({ size = 28 }: { size?: number }) {
  const gid = useId();
  return (
    <span style={{ display: "inline-flex", width: size, height: size, filter: "drop-shadow(0 0 10px rgba(0,212,170,0.35))" }}>
      <svg viewBox="0 0 32 32" width={size} height={size} aria-hidden>
        <defs>
          <linearGradient id={gid} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#00e5b0" />
            <stop offset="1" stopColor="#0090cc" />
          </linearGradient>
        </defs>
        <path d="M16 1.5 L29 9 V23 L16 30.5 L3 23 V9 Z" fill={`url(#${gid})`} />
        <path
          d="M11 19.5 v-6 a5 5 0 1 1 10 0 v6 M8.5 22 h5 M18.5 22 h5"
          fill="none"
          stroke="#06281f"
          strokeWidth="2.4"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </span>
  );
}

export function BrandName({ size = 16 }: { size?: number }) {
  return (
    <span style={{ fontWeight: 800, fontSize: size, letterSpacing: "0.02em", whiteSpace: "nowrap" }}>
      Omni<span style={{ color: "var(--accent)" }}>Alpha</span>
    </span>
  );
}
