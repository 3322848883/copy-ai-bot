"use client";

/** M2 T2.8：5 大交易所标签页骨架（Gate 接入，其余"待接入"占位）。 */
const EXCHANGES = [
  { key: "gate", name: "Gate", ready: true },
  { key: "binance", name: "Binance", ready: false },
  { key: "okx", name: "OKX", ready: false },
  { key: "bybit", name: "Bybit", ready: false },
  { key: "bitget", name: "Bitget", ready: false },
];

export default function ExchangeTabs({
  current,
  onChange,
}: {
  current: string;
  onChange: (key: string) => void;
}) {
  return (
    <div style={{ display: "flex", gap: 8, marginBottom: 20, flexWrap: "wrap" }}>
      {EXCHANGES.map((ex) => {
        const active = current === ex.key;
        return (
          <button
            key={ex.key}
            onClick={() => ex.ready && onChange(ex.key)}
            disabled={!ex.ready}
            title={ex.ready ? ex.name : `${ex.name} 待接入`}
            style={{
              padding: "8px 20px",
              borderRadius: 6,
              border: active ? "1px solid var(--accent)" : "1px solid var(--rule)",
              background: active ? "var(--accent-soft)" : "var(--surface)",
              color: active ? "var(--accent)" : ex.ready ? "var(--fg)" : "var(--tertiary)",
              cursor: ex.ready ? "pointer" : "not-allowed",
              fontWeight: 600,
              fontSize: 14,
              opacity: ex.ready ? 1 : 0.55,
            }}
          >
            {ex.name}
            {!ex.ready && <span style={{ marginLeft: 6, fontSize: 11 }}>待接入</span>}
          </button>
        );
      })}
    </div>
  );
}
