// 时间格式化：后端 isoformat 为 UTC，直接 slice 字符串会把北京时间显示成 8 小时前。
// 统一经 Date 转换为浏览器本地时区后再取日期/时刻。

function parse(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

const p = (n: number) => String(n).padStart(2, "0");

/** YYYY-MM-DD（本地时区），无效/空返回 null */
export function localDate(iso?: string | null): string | null {
  const d = parse(iso);
  return d ? `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}` : null;
}

/** YYYY-MM-DD HH:mm（本地时区），无效/空返回 "—" */
export function localDateTime(iso?: string | null): string {
  const d = parse(iso);
  return d ? `${localDate(iso)} ${p(d.getHours())}:${p(d.getMinutes())}` : "—";
}

/** MM-DD（本地时区），用于图表区间标签 */
export function localMonthDay(iso?: string | null): string {
  const d = parse(iso);
  return d ? `${p(d.getMonth() + 1)}-${p(d.getDate())}` : "—";
}
