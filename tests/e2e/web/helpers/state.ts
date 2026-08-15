import fs from "fs";
import path from "path";

/** 读取 API 阶段产出的 state.json（含邮箱/订单/策略 id 等）。 */
export function readState(): Record<string, any> {
  const p = path.resolve(__dirname, "../../state.json");
  if (!fs.existsSync(p)) {
    throw new Error(`state.json 不存在: ${p}，请先运行 API 自动化套件`);
  }
  return JSON.parse(fs.readFileSync(p, "utf-8"));
}

/** 从 mailhog 读取验证码（Node 版，mailhog v1 API 返回 JSON 数组）。 */
export async function readMailhogCode(email: string, timeoutMs = 30000): Promise<string> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const resp = await fetch("http://localhost:8025/api/v1/messages");
    const data: any[] = await resp.json();
    for (const item of data) {
      const to = (item?.Content?.Headers?.To?.[0] ?? "") as string;
      if (to.toLowerCase().includes(email.toLowerCase())) {
        // 优先用 content 端点拿解码后的 HTML
        const id = item?.ID;
        if (id) {
          try {
            const cr = await fetch(`http://localhost:8025/api/v1/messages/${id}/content`);
            const cdata: any = await cr.json();
            const m = (cdata?.HTML ?? "").match(/>\s*(\d{6})\s*<\/div>/);
            if (m) return m[1];
          } catch {
            /* fallthrough to raw */
          }
        }
        // 兜底：Raw.Data 中 base64 解码 HTML 后匹配
        const raw: string = item?.Raw?.Data ?? item?.Content?.Body ?? "";
        const b64Match = raw.match(/Content-Transfer-Encoding: base64\r?\n\r?\n([A-Za-z0-9+/=\r\n]+)/);
        if (b64Match) {
          const html = Buffer.from(b64Match[1].replace(/\s/g, ""), "base64").toString("utf-8");
          const m = html.match(/>\s*(\d{6})\s*<\/div>/);
          if (m) return m[1];
        }
      }
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error(`mailhog 30s 内未收到 ${email} 的验证码`);
}

/** 生成时间戳邮箱。 */
export function mkEmail(prefix: string): string {
  return `e2e_${prefix}_${Date.now()}@t.com`;
}
