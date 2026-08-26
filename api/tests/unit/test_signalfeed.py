# 符号 feed 差分引擎单元测试
# 覆盖：基线建立 / 开平仓差分 / 阈值过滤 / 全量对账 / 旧格式状态兼容
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from types import SimpleNamespace


from api.services.signalfeed.service import IncrementalFeedService


class FakeRedis:
    """内存版 redis 客户端，仅实现本服务用到的接口。"""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._store[key] = value

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)


class FakeScraper:
    """可控返回持仓快照的假 scraper。"""

    def __init__(self, snapshots: list[dict[str, float] | None]) -> None:
        self._snapshots = list(snapshots)
        self.calls = 0

    async def fetch_live_positions(self, trader_id: str) -> dict[str, float] | None:
        self.calls += 1
        if self._snapshots:
            return self._snapshots.pop(0)
        return None


def make_service(scraper: FakeScraper, threshold: float = 0.0, reconcile: int = 600) -> IncrementalFeedService:
    """构造服务：注入假 redis + 假 scraper，并覆盖阈值/对账间隔。"""
    svc = IncrementalFeedService(db=None, redis=FakeRedis(), scraper=scraper)
    svc.threshold = threshold
    svc.reconcile_interval = reconcile
    return svc


def run(coro):
    return asyncio.run(coro)


def test_first_poll_builds_baseline_no_signals():
    """首次轮询只建基线，存量持仓不产出信号。"""
    svc = make_service(FakeScraper([{"BTC_USDT": 0.4, "ETH_USDT": 0.3}]))
    events = run(svc.poll_leader("1001"))
    assert events == []
    state = run(svc.get_state("1001"))
    assert state["pos"] == {"BTC_USDT": 0.4, "ETH_USDT": 0.3}
    assert state["ts"] is not None


def test_open_and_close_detection():
    """第二次轮询：新出现→open，消失→close，不变→忽略。"""
    svc = make_service(FakeScraper([
        {"BTC_USDT": 0.4, "ETH_USDT": 0.3},  # 基线
        {"BTC_USDT": 0.4, "SOL_USDT": 0.2},  # ETH 消失，SOL 新增
    ]))
    run(svc.poll_leader("1001"))  # 基线
    events = run(svc.poll_leader("1001"))
    actions = {(e.symbol, e.action): e for e in events}
    assert ("SOL_USDT", "open") in actions
    assert ("ETH_USDT", "close") in actions
    assert ("BTC_USDT", "open") not in actions
    assert ("BTC_USDT", "close") not in actions
    # open 事件带 percent
    assert actions[("SOL_USDT", "open")].percent == 0.2


def test_empty_position_fully_closes():
    """真空仓 {} → 全部 close。"""
    svc = make_service(FakeScraper([
        {"BTC_USDT": 0.4},
        {},
    ]))
    run(svc.poll_leader("1001"))
    events = run(svc.poll_leader("1001"))
    assert [(e.symbol, e.action) for e in events] == [("BTC_USDT", "close")]


def test_api_failure_skips_round():
    """接口失败(None) → 跳过本轮，不更新基线。"""
    svc = make_service(FakeScraper([
        {"BTC_USDT": 0.4},  # 基线
        None,               # 接口失败
        {"BTC_USDT": 0.4},  # 恢复正常
    ]))
    run(svc.poll_leader("1001"))
    assert run(svc.poll_leader("1001")) == []  # 失败跳过
    state = run(svc.get_state("1001"))
    assert state["pos"] == {"BTC_USDT": 0.4}


def test_threshold_filters_tiny_positions():
    """阈值过滤：低于阈值的微仓不触发 open，跨过阈值才触发。"""
    svc = make_service(FakeScraper([
        {"BTC_USDT": 0.4},                          # 基线
        {"BTC_USDT": 0.4, "DOGE_USDT": 0.002},      # DOGE 0.2% < 0.5% → 过滤
        {"BTC_USDT": 0.4, "DOGE_USDT": 0.01},       # DOGE 1% ≥ 0.5% → open
    ]), threshold=0.005)
    run(svc.poll_leader("1001"))  # 基线
    run(svc.poll_leader("1001"))  # DOGE 0.2% 被过滤，无事件
    events = run(svc.poll_leader("1001"))  # DOGE 1% 触发 open
    assert [(e.symbol, e.action) for e in events] == [("DOGE_USDT", "open")]


def test_reconcile_leader_emits_corrections():
    """全量对账：与最新持仓 diff，产出修正事件并重设基线。"""
    svc = make_service(FakeScraper([
        {"BTC_USDT": 0.4},             # 基线
        {"BTC_USDT": 0.4, "SOL_USDT": 0.3},  # 对账发现 SOL 新增
    ]))
    run(svc.poll_leader("1001"))
    events = run(svc.reconcile_leader("1001"))
    assert [(e.symbol, e.action) for e in events] == [("SOL_USDT", "open")]
    state = run(svc.get_state("1001"))
    assert "SOL_USDT" in state["pos"]


def test_reconcile_leader_no_baseline_builds():
    """对账无基线时建立基线，不产出。"""
    svc = make_service(FakeScraper([{"BTC_USDT": 0.4}]))
    assert run(svc.reconcile_leader("1001")) == []
    state = run(svc.get_state("1001"))
    assert state["pos"] == {"BTC_USDT": 0.4}


def test_old_format_state_compatible():
    """兼容旧版纯 dict 快照（无 ts）：能正常读取并 diff。"""
    svc = make_service(FakeScraper([
        {"BTC_USDT": 0.4, "SOL_USDT": 0.3},
    ]))
    # 直接写入旧格式状态
    run(svc.set_state("1001", {"BTC_USDT": 0.4}))
    events = run(svc.poll_leader("1001"))
    assert [(e.symbol, e.action) for e in events] == [("SOL_USDT", "open")]


def test_stale_baseline_triggers_reconcile_log():
    """基线过旧(超过 reconcile_interval)仍正常 diff 并更新基线。"""
    svc = make_service(FakeScraper([
        {"BTC_USDT": 0.4, "SOL_USDT": 0.3},
    ]), reconcile=10)
    # 写入一个很旧的基线(ts 早于当前 100s)
    asyncio.run(svc.set_state("1001", {"BTC_USDT": 0.4}, ts=time.time() - 100))
    events = run(svc.poll_leader("1001"))
    assert [(e.symbol, e.action) for e in events] == [("SOL_USDT", "open")]
    state = run(svc.get_state("1001"))
    assert time.time() - state["ts"] < 5  # 基线已刷新


class BatchFakeScraper:
    """支持 fetch_live_positions_many 的假 scraper：按轮次返回多交易员快照。"""

    def __init__(self, rounds: list[dict[str, dict[str, float] | None]]) -> None:
        self._rounds = list(rounds)
        self.batch_calls = 0

    async def fetch_live_positions_many(self, trader_ids: list[str]) -> dict[str, dict[str, float] | None]:
        self.batch_calls += 1
        if self._rounds:
            return self._rounds.pop(0)
        return {tid: None for tid in trader_ids}


def test_poll_leaders_many_batch_concurrent():
    """批量并发轮询：一次调用同时处理多个交易员，各自独立 diff。"""
    svc = make_service(BatchFakeScraper([
        # 第 1 轮：A/B 建基线
        {"A": {"BTC_USDT": 0.4}, "B": {"ETH_USDT": 0.3}},
        # 第 2 轮：A 加 SOL，B 平 ETH
        {"A": {"BTC_USDT": 0.4, "SOL_USDT": 0.2}, "B": {}},
    ]))
    m1 = run(svc.poll_leaders_many(["A", "B"]))
    assert all(v == [] for v in m1.values())  # 首轮建基线，无事件
    m2 = run(svc.poll_leaders_many(["A", "B"]))
    assert [(e.symbol, e.action) for e in m2["A"]] == [("SOL_USDT", "open")]
    assert [(e.symbol, e.action) for e in m2["B"]] == [("ETH_USDT", "close")]


def test_poll_leaders_many_partial_failure():
    """批量轮询中某交易员接口失败(None) → 该交易员空事件，不影响其他。"""
    svc = make_service(BatchFakeScraper([
        {"A": {"BTC_USDT": 0.4}, "B": {"ETH_USDT": 0.3}},  # 第 1 轮建基线
        {"A": {"BTC_USDT": 0.4, "SOL_USDT": 0.2}, "B": None},  # B 失败
    ]))
    run(svc.poll_leaders_many(["A", "B"]))
    m2 = run(svc.poll_leaders_many(["A", "B"]))
    assert [(e.symbol, e.action) for e in m2["A"]] == [("SOL_USDT", "open")]
    assert m2["B"] == []  # B 接口失败，跳过
    assert svc.scraper.batch_calls == 2  # 两次批量调用（并发拉取），非逐交易员拉取


def test_reconcile_leaders_many_batch():
    """批量并发对账：多交易员各自与基线对齐产出修正事件。"""
    svc = make_service(BatchFakeScraper([
        {"A": {"BTC_USDT": 0.4}, "B": {"ETH_USDT": 0.3}},  # 第 1 轮建基线
        {"A": {"BTC_USDT": 0.4, "SOL_USDT": 0.3}, "B": {}},  # 对账：A 加 SOL，B 平 ETH
    ]))
    run(svc.poll_leaders_many(["A", "B"]))
    m = run(svc.reconcile_leaders_many(["A", "B"]))
    assert [(e.symbol, e.action) for e in m["A"]] == [("SOL_USDT", "open")]
    assert [(e.symbol, e.action) for e in m["B"]] == [("ETH_USDT", "close")]


# ── 模式2 信号源：follower/position 解析（★ 真实报文字段口径）──
#   核心守则：跟单模式只监控「自己已跟单」的镜像仓位，且必须按顶层 leader_id 精确归属。
#   带单员隐藏公开仓位信息不影响模式2——镜像仓位始终可见、方向真实。
def _gate_scraper():
    from api.services.scraper.adapters.gate import GateScraper
    return GateScraper(mock=True)


def test_parse_follower_pos_takes_top_level_leader_id():
    """★ 归属守则：leader_id 取数据行顶层（int 32801），不在 trader_info 里。

    若误取 trader_info.leader_id（不存在）→ 归属为空 → 无法按带单员隔离，
    会与跟单账户里其他带单员的仓位混淆（带单员隐藏仓位时尤为致命）。
    """
    scraper = _gate_scraper()
    resp = {
        "code": 200,
        "data": [{
            "id": 17695298, "leader_id": 32801, "follow_id": 871675,
            "market": "ETH_USDT", "size": 0, "sizes": "0.1",
            "qty": "0.001", "entry_price": "1886.04", "side": "short",
            "leverage": "0", "cross_leverage_limit": "50",
            "trader_info": {"nick": "复利如慢牛", "anonymous": "Judy-..."},
        }],
    }
    parsed = scraper._parse_follower_positions(resp)
    assert len(parsed) == 1
    p = parsed[0]
    assert p.trader_id == "32801"          # ★ 顶层 leader_id，非空
    assert p.symbol == "ETHUSDT"           # _ → 去下划线
    assert p.side == "short"               # 真实方向
    assert p.qty == 0.001                  # ★ 跟单数量 qty，非 size
    assert p.leverage == 50                # ★ leverage="0" 回退 cross_leverage_limit


def test_parse_follower_pos_preserves_gate_open_time():
    """模式B必须使用 Gate 源时间，不能把采集时刻伪装成带单员开仓时间。"""
    scraper = _gate_scraper()
    source_ts = 1_777_000_000
    resp = {
        "code": 200,
        "data": [{
            "leader_id": 32801, "market": "ETH_USDT", "qty": "0.001",
            "side": "long", "entry_price": "1886.04", "leverage": "10",
            "open_time": source_ts,
        }],
    }
    parsed = scraper._parse_follower_positions(resp)
    assert parsed[0].opened_at == datetime.fromtimestamp(source_ts, tz=timezone.utc)


def test_poll_follower_open_event_uses_source_time():
    """镜像仓位新出现时，FeedEvent.at 应等于源仓位时间。"""
    source_at = datetime(2026, 8, 26, 1, 2, 3, tzinfo=timezone.utc)

    class FollowerScraper:
        def __init__(self):
            self.round = 0

        async def fetch_follower_positions_many(self, leader_ids):
            self.round += 1
            if self.round == 1:
                return {"32801": []}
            pos = SimpleNamespace(
                symbol="ETHUSDT", qty=0.001, side="long", opened_at=source_at,
            )
            return {"32801": [pos]}

    svc = make_service(FollowerScraper())
    assert run(svc.poll_followers_many(["32801"]))["32801"] == []
    events = run(svc.poll_followers_many(["32801"]))["32801"]
    assert len(events) == 1
    assert events[0].at == source_at


def test_mode_b_small_quantity_is_not_filtered_by_mode_a_percent_threshold():
    """模式B的 0.001 ETH 是有效数量，不能被模式A的 0.5%阈值过滤。"""
    source_at = datetime(2026, 8, 26, 1, 2, 3, tzinfo=timezone.utc)

    class FollowerScraper:
        def __init__(self):
            self.round = 0

        async def fetch_follower_positions_many(self, leader_ids):
            self.round += 1
            if self.round == 1:
                return {"32801": []}
            return {"32801": [SimpleNamespace(
                symbol="ETHUSDT", qty=0.001, side="long", opened_at=source_at,
            )]}

    svc = make_service(FollowerScraper(), threshold=0.005)
    run(svc.poll_followers_many(["32801"]))
    events = run(svc.poll_followers_many(["32801"]))["32801"]
    assert [(e.symbol, e.action) for e in events] == [("ETHUSDT", "open")]


def test_mode_b_same_symbol_quantity_changes_emit_add_and_reduce():
    """同一币种连续开单会聚合到持仓数量，差分必须生成同比例加仓/减仓。"""
    class FollowerScraper:
        def __init__(self):
            self.quantities = iter([1.0, 1.5, 0.75])

        async def fetch_follower_positions_many(self, leader_ids):
            qty = next(self.quantities)
            return {"32801": [SimpleNamespace(
                symbol="MSTRXUSDT", qty=qty, side="short", opened_at=None,
            )]}

    svc = make_service(FollowerScraper())
    assert run(svc.poll_followers_many(["32801"]))["32801"] == []
    added = run(svc.poll_followers_many(["32801"]))["32801"]
    reduced = run(svc.poll_followers_many(["32801"]))["32801"]
    assert [(e.action, e.percent, e.side) for e in added] == [("add", 0.5, "short")]
    assert [(e.action, e.percent, e.side) for e in reduced] == [("reduce", 0.5, "short")]


def test_mode_a_weight_fluctuation_does_not_emit_add_or_reduce():
    """公开组合占比会随价格波动，模式 A 不得把占比变化误当成真实加减仓。"""
    events = IncrementalFeedService._diff(
        "32801", {"BTCUSDT": 0.20}, {"BTCUSDT": 0.25}, emit_size_changes=False,
    )
    assert events == []


def test_mode_b_direction_flip_emits_close_then_open_with_real_sides():
    """同一币种由多翻空，即使数量不变，也必须先平多再开空。"""
    class FollowerScraper:
        def __init__(self):
            self.sides = iter(["long", "short"])

        async def fetch_follower_positions_many(self, leader_ids):
            side = next(self.sides)
            return {"32801": [SimpleNamespace(
                symbol="MSTRXUSDT", qty=23.76, side=side, opened_at=None,
            )]}

    svc = make_service(FollowerScraper())
    assert run(svc.poll_followers_many(["32801"]))["32801"] == []
    events = run(svc.poll_followers_many(["32801"]))["32801"]
    assert [(e.action, e.side) for e in events] == [("close", "long"), ("open", "short")]


def test_parse_follower_pos_multi_trader_isolated():
    """★ 多带单员镜像仓位混在跟单账户 → 按顶层 leader_id 隔离，绝不可混淆。"""
    scraper = _gate_scraper()
    resp = {
        "code": 200,
        "data": [
            {"leader_id": 32801, "market": "ETH_USDT", "qty": "0.001",
             "side": "short", "entry_price": "1886.04", "leverage": "0",
             "cross_leverage_limit": "50", "trader_info": {"nick": "复利如慢牛"}},
            {"leader_id": 32802, "market": "BTC_USDT", "qty": "0.002",
             "side": "long", "entry_price": "60000", "leverage": "0",
             "cross_leverage_limit": "20", "trader_info": {"nick": "另一带单员"}},
        ],
    }
    parsed = scraper._parse_follower_positions(resp)
    by_id = {p.trader_id: p for p in parsed}
    assert set(by_id) == {"32801", "32802"}  # ★ 两个带单员各自隔离
    assert by_id["32801"].symbol == "ETHUSDT"
    assert by_id["32802"].symbol == "BTCUSDT"


def test_parse_follower_pos_filters_test_symbols():
    """★ 测试符号过滤：symbol 含 TEST/DEMO/FAKE 即丢弃。"""
    scraper = _gate_scraper()
    resp = {
        "code": 200,
        "data": [
            {"leader_id": 32801, "market": "ETH_USDT", "qty": "0.001",
             "side": "short", "leverage": "0", "cross_leverage_limit": "50"},
            {"leader_id": 32801, "market": "TESTUSDT", "qty": "0.001",
             "side": "long", "leverage": "0", "cross_leverage_limit": "50"},
        ],
    }
    parsed = scraper._parse_follower_positions(resp)
    assert [p.symbol for p in parsed] == ["ETHUSDT"]


def test_fetch_followed_leaders_discovers_empty_position_trader():
    """★ 自动发现：follow/order 返回全部已跟单交易员（含空仓的 leader_id+昵称）。

    空仓交易员在 position 接口不出现，只能靠 follow/order 发现——这正是
    「跟单了两个交易员但仓位只有一个」场景下不漏跟单的关键。
    """
    # mock 路径直接返回两个已跟单交易员（32801 复利如慢牛 有仓、24264 风懃 空仓）
    scraper = _gate_scraper()
    leaders = asyncio.run(scraper.fetch_followed_leaders())
    assert set(leaders) == {("32801", "复利如慢牛"), ("24264", "风懃")}


def test_search_leaders_by_nick_parses_profile():
    """★ 按昵称搜索带单员：解析 leader/search 返回的画像（参数名是 name 非 keyword）。"""
    scraper = _gate_scraper()
    scraper.mock = False

    async def fake_api(path, params, page=None):
        assert path == "/apiw/v2/copy/leader/search"
        assert params == {"name": "风懃", "page": 1, "page_size": 20}
        return {
            "code": 0,
            "data": {"list": [
                {"leader_id": 24264, "profit_rate": "3.2", "win_rate": "0.61",
                 "max_drawdown": "0.05", "curr_follow_num": 1, "is_follow": True,
                 "is_full": False,
                 "user_info": {"nick": "风懃"}},
            ]},
        }

    scraper._api = fake_api
    # ★ 方案B：私有接口默认走登录会话；这里显式传 self._api 走公开解析路径（单测）
    items = asyncio.run(scraper.search_leaders("风懃", fetcher=scraper._api))
    assert items is not None and len(items) == 1
    it = items[0]
    assert it["leader_id"] == 24264
    assert it["nick"] == "风懃"
    assert it["roi_30d"] == 320.0        # profit_rate 3.2 → *100
    assert it["win_rate_all"] == 61.0    # 0.61 → 61
    assert it["max_drawdown"] == 5.0     # 0.05 → 5
    assert it["followers"] == 1
    assert it["is_follow"] is True


def test_search_leaders_empty_keyword_returns_empty():
    """空关键字→空列表，不调接口。"""
    scraper = _gate_scraper()
    assert asyncio.run(scraper.search_leaders("  ")) == []
    assert asyncio.run(scraper.search_leaders("")) == []


def test_get_leader_by_id_detail_parses_profile():
    """★ 按 ID 精确查兜底：解析 trader/detail 返回的画像（含风格/简介/交易标的）。"""
    scraper = _gate_scraper()
    scraper.mock = False
    captured = {}

    async def fake_api(path, params, page=None):
        assert path == "/api/copytrade/copy_trading/trader/detail/24264"
        assert params == {"sub_website_id": 0}
        captured["path"] = path
        return {
            "code": 200,
            "data": {
                "config": {"leader_id": 24264, "style": "high-frequence|short-line",
                           "abstract": "顺势而为", "min_follow_amount": "10",
                           "max_follow_amount": "50000",
                           "markets": [{"market": "BTC_USDT"}, {"market": "ETH_USDT"}]},
                "profit": {"profit_rate": "-0.6442", "month_profit_rate": "-0.1268",
                           "seven_profit_rate": "0.02", "three_month_profit_rate": "-0.8366",
                           "win_num": 174, "loss_num": 260, "month_win_rate": "0.9514",
                           "curr_follow_num": 1, "max_drawdown": "0.3477",
                           "duration_day": "120", "is_full": 0},
            },
        }

    scraper._api = fake_api
    # ★ 方案B：私有接口默认走登录会话；这里显式传 self._api 走公开解析路径（单测）
    it = asyncio.run(scraper.get_leader_by_id("24264", fetcher=scraper._api))
    assert it is not None
    assert it["leader_id"] == "24264"
    assert it["roi_7d"] == 2.0             # seven_profit_rate 0.02 → 2
    assert it["roi_30d"] == -12.68          # month_profit_rate -0.1268 → -12.68
    assert it["roi_90d"] == -83.66          # three_month_profit_rate -0.8366 → -83.66
    assert it["roi_all"] == -64.42          # profit_rate -0.6442 → -64.42
    assert it["win_rate_30d"] == 95.14      # month_win_rate 0.9514 → 95.14
    assert it["win_rate_all"] == 40.1          # 174/434
    assert it["max_drawdown"] == 34.77
    assert it["followers"] == 1
    assert it["style"] == "high-frequence|short-line"
    assert it["abstract"] == "顺势而为"
    assert it["markets"] == ["BTC_USDT", "ETH_USDT"]
    assert it["min_follow_amount"] == "10"


def test_get_leader_by_id_rejects_non_digit():
    """非纯数字 ID → None，不调接口。"""
    scraper = _gate_scraper()
    assert asyncio.run(scraper.get_leader_by_id("abc")) is None
    assert asyncio.run(scraper.get_leader_by_id("")) is None
