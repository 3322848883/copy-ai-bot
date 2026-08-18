"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

/** 平台公开配置（/v1/config）：后台改规则后前台即刻同步。 */

export type PlatformConfig = {
  referral: { reward_pct: number; verify_hours: number; abuse_verify_hours: number };
  chain_confirmations: { trc20: number; bep20: number; erc20: number; aptos: number };
  payment: { order_ttl_min: number; fee_tolerance_usdt: number };
  withdraw: { min_withdrawal_usdt: number; fee_usdt: number };
  support: { email: string; telegram: string };
};

// 接口不可达时兜底（与后端 PLATFORM_RULES 默认值一致，仅降级展示用）
const FALLBACK: PlatformConfig = {
  referral: { reward_pct: 10, verify_hours: 24, abuse_verify_hours: 48 },
  chain_confirmations: { trc20: 12, bep20: 15, erc20: 32, aptos: 20 },
  payment: { order_ttl_min: 30, fee_tolerance_usdt: 2 },
  withdraw: { min_withdrawal_usdt: 10, fee_usdt: 1 },
  support: { email: "", telegram: "" },
};

let cache: PlatformConfig | null = null;
let inflight: Promise<PlatformConfig> | null = null;

function fetchConfig(): Promise<PlatformConfig> {
  if (cache) return Promise.resolve(cache);
  if (!inflight) {
    inflight = apiFetch<PlatformConfig>("/v1/config")
      .then((c) => {
        cache = c;
        return c;
      })
      .catch(() => FALLBACK);
  }
  return inflight;
}

/** 页面级 hook：模块级缓存，多页复用只发一次请求。 */
export function usePlatformConfig(): PlatformConfig {
  const [cfg, setCfg] = useState<PlatformConfig>(cache ?? FALLBACK);
  useEffect(() => {
    let alive = true;
    fetchConfig().then((c) => {
      if (alive) setCfg(c);
    });
    return () => {
      alive = false;
    };
  }, []);
  return cfg;
}
