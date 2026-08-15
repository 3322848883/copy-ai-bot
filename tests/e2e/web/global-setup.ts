import { execSync } from "child_process";

const DOCKER = process.env.DOCKER_BIN || "C:\\Program Files\\Docker\\Docker\\resources\\bin\\docker.exe";

/** 测试前清理：清 Redis 限流键（避免 /v1/auth/ 10次/分/IP 触发 429）。
 * 仅当 docker 可用时执行；失败不阻断（限流键会自然过期）。 */
export default function globalSetup() {
  try {
    const out = execSync(
      `"${DOCKER}" exec ai-redis-1 redis-cli -n 0 --scan --pattern "ratelimit:*"`,
      { encoding: "utf-8", timeout: 15000, shell: "cmd.exe" }
    );
    const keys = out.split("\n").map((s) => s.trim()).filter(Boolean);
    for (const k of keys) {
      execSync(`"${DOCKER}" exec ai-redis-1 redis-cli -n 0 DEL "${k}"`, { timeout: 10000, shell: "cmd.exe" });
    }
    console.log(`[global-setup] cleared ${keys.length} ratelimit keys`);
  } catch (e: any) {
    console.warn("[global-setup] ratelimit cleanup skipped:", e?.message ?? e);
  }
}
