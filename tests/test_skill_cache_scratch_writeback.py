"""test_skill_cache_scratch_writeback.py — cache 命中回写 scratch 回归.

背景: 节点热补丁 (2026-09 运维侧) — skills/_runtime.py execute() 在
AgentCache 命中时直接 return cached, 不回写 ctx.scratch; 同一 ctx 的
多 skill 链路 (parse_rfq -> calc_quote -> ...) 第二次起后续 skill
拿不到 rfq/specs/quote/dfm。本测试锁定回灌行为。
"""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def rt_with_cache(tmp_root: Path):
    """隔离 cache 单例到 tmp_root, 返回 skills._runtime 模块."""
    from services import agent_cache
    from services.agent_cache import AgentCache
    import skills._runtime as rt

    agent_cache.reset_global()
    agent_cache._global = AgentCache(root=tmp_root)
    yield rt
    rt._REGISTRY.pop("_t_writeback_probe", None)
    agent_cache.reset_global()


def _install_fake(rt):
    calls = {"n": 0}

    def fake_skill(ctx, **kw):
        calls["n"] += 1
        # 真 skill 形态: 中间产物既写 scratch 也放返回值 (parse_rfq/
        # calc_quote 等返回 rfq/specs/quote), 缓存存的是返回值
        ctx.scratch["rfq"] = {"part": "法兰", "qty": 2}
        ctx.scratch["quote"] = {"total": 1996.99}
        return {"ok": True, "val": 42,
                "rfq": {"part": "法兰", "qty": 2},
                "quote": {"total": 1996.99}}

    rt._REGISTRY["_t_writeback_probe"] = fake_skill
    return calls


def test_cache_hit_writebacks_scratch(rt_with_cache) -> None:
    rt = rt_with_cache
    calls = _install_fake(rt)

    ctx1 = rt.SkillContext()
    out1 = rt.execute("_t_writeback_probe", {"a": 1}, ctx1)
    assert out1["_cache"] == "miss"
    assert out1["val"] == 42
    assert ctx1.scratch["rfq"] == {"part": "法兰", "qty": 2}

    # 第二次: 新 ctx + 同 args → 缓存命中; scratch 必须拿到回写
    ctx2 = rt.SkillContext()
    out2 = rt.execute("_t_writeback_probe", {"a": 1}, ctx2)
    assert out2["_cache"] == "hit"
    assert out2["val"] == 42
    assert calls["n"] == 1, "缓存未生效: skill 被重跑"
    assert ctx2.scratch.get("rfq") == {"part": "法兰", "qty": 2}, (
        "cache hit 未回写 ctx.scratch — 后续 skill 拿不到中间产物"
    )
    assert ctx2.scratch.get("quote") == {"total": 1996.99}


def test_cache_hit_does_not_clobber_existing_scratch(rt_with_cache) -> None:
    rt = rt_with_cache
    _install_fake(rt)

    rt.execute("_t_writeback_probe", {"a": 1}, rt.SkillContext())

    ctx = rt.SkillContext()
    ctx.scratch["rfq"] = {"part": "已存在", "qty": 99}
    rt.execute("_t_writeback_probe", {"a": 1}, ctx)
    assert ctx.scratch["rfq"] == {"part": "已存在", "qty": 99}, (
        "cache hit 回写不得覆盖 ctx 已有 scratch"
    )
