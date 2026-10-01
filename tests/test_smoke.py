"""冒烟 + 行为测试。

覆盖契约「message_reaction 行为」表的每一行，以及 with_reaction 对 NoneBot
控制流异常的判定。全部用 fake event + monkeypatch ``nonebot_plugin_alconna.uniseg``
完成，不连真实 QQ。
运行: uv run pytest tests/ -q
"""

import asyncio
import importlib.util
import logging
from types import SimpleNamespace
from typing import Any

import nonebot
from nonebot.exception import FinishedException
from nonebot.matcher import current_event
from nonebot_plugin_alconna import uniseg
import pytest

from nonebot_plugin_message_reaction import (
    EMOJI_MAP,
    message_reaction,
    with_reaction,
)

nonebot.init()
nonebot.load_plugin("nonebot_plugin_message_reaction")

_LOGGER_NAME = "nonebot_plugin_message_reaction"

_REAL_FIND_SPEC = importlib.util.find_spec


class _Recorder:
    """记录 uniseg.message_reaction 被调用时发出的 (emoji, message_id)，可注入异常。"""

    def __init__(self, *, raise_exc: BaseException | None = None) -> None:
        self.calls: list[tuple[str, str | None]] = []
        self.raise_exc = raise_exc

    async def message_reaction(
        self,
        emoji: str,
        message_id: str | None = None,
        **_kwargs: Any,
    ) -> None:
        self.calls.append((emoji, message_id))
        if self.raise_exc is not None:
            raise self.raise_exc


def _patch_uniseg(
    monkeypatch: pytest.MonkeyPatch,
    *,
    adapter: str = "OneBot V11",
    raise_exc: BaseException | None = None,
    private_override: bool | None = None,
) -> _Recorder:
    """把 uniseg 的取 id / 取 target / 表态三个入口替换为可断言的假实现。

    ``get_target().private`` 依据事件是否带 group_id 推导（模拟真实语义），
    这样带 group_id 的群聊事件判为非私聊、不带 group_id 的私聊事件判为私聊。
    """
    recorder = _Recorder(raise_exc=raise_exc)

    def _get_target(event: Any) -> Any:
        private = (
            private_override
            if private_override is not None
            else getattr(event, "group_id", None) is None
        )
        return SimpleNamespace(private=private, adapter=adapter)

    monkeypatch.setattr(uniseg, "get_message_id", lambda _event: "mid-1")
    monkeypatch.setattr(uniseg, "get_target", _get_target)
    monkeypatch.setattr(uniseg, "message_reaction", recorder.message_reaction)
    return recorder


def _group_event() -> SimpleNamespace:
    return SimpleNamespace(group_id=123456)


def _private_event() -> SimpleNamespace:
    return SimpleNamespace(user_id=654321)


# ---------------------------------------------------------------------------
# 契约表第 1 行：私聊（event 无 group_id）→ 直接返回 False，不发、不报错
# ---------------------------------------------------------------------------


def test_private_chat_returns_false_and_never_sends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """契约表「私聊」行：无 group_id 时必须直接 False，且不调用 uniseg 表态。

    防的 bug：私聊没有 group_id，若照常调用 set_group_reaction 会抛错，把
    表态变成主流程的异常源；QQ 平台私聊本就不支持表态。
    """
    recorder = _patch_uniseg(monkeypatch, private_override=True)
    result = asyncio.run(message_reaction(_private_event(), "done"))
    assert result is False
    assert recorder.calls == []


def test_private_chat_without_alconna_context_still_returns_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """契约表「私聊（event 无 group_id）」行：alconna 无 Bot 上下文时靠 group_id 兜底。

    只替换表态入口，不替换 get_target —— 真实 get_target 在无 Bot 上下文会抛错，
    实现必须退化为「无 group_id 即私聊」，而不是把异常当失败去 warning。
    """
    recorder = _Recorder()
    monkeypatch.setattr(uniseg, "message_reaction", recorder.message_reaction)
    result = asyncio.run(message_reaction(_private_event(), "done"))
    assert result is False
    assert recorder.calls == []


# ---------------------------------------------------------------------------
# 契约表第 2 行：缺 alconna → logger.warning 一次 + 返回 False，绝不抛
# ---------------------------------------------------------------------------


def test_missing_alconna_warns_once_and_returns_false(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """契约表「缺 alconna」行：缺依赖只 warning 一次并返回 False，绝不抛出。

    防的 bug：没装 alconna 时 ImportError 冒到 handler，把主功能整个搞挂。
    """

    def _fake_find_spec(name: str, *_a: Any, **_k: Any) -> Any:
        if name == "nonebot_plugin_alconna":
            return None
        return _REAL_FIND_SPEC(name, *_a, **_k)

    monkeypatch.setattr(importlib.util, "find_spec", _fake_find_spec)
    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        result = asyncio.run(message_reaction(_group_event(), "done"))
    assert result is False
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1


# ---------------------------------------------------------------------------
# 契约表第 3 行：发表态抛任何异常 → logger.warning + 返回 False，绝不抛
# ---------------------------------------------------------------------------


def test_send_exception_is_swallowed_as_false(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """契约表「发表态抛任何异常」行：底层表态实现/权限静默失败时只 warning + False。

    防的 bug：LLBot/权限不支持时表态会抛 ActionFailed，若不上报 False 反而
    向外抛，一个表情会把「获取全文」这类主功能整个搞挂。
    """
    _patch_uniseg(monkeypatch, raise_exc=RuntimeError("unsupported"))
    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        result = asyncio.run(message_reaction(_group_event(), "resolving"))
    assert result is False
    assert any(r.levelno == logging.WARNING for r in caplog.records)


# ---------------------------------------------------------------------------
# 契约表第 4 行：成功发出 → True（并断言发出的 emoji）
# ---------------------------------------------------------------------------


def test_group_success_returns_true_with_message_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """契约表「成功发出」行：群聊 + OneBot 系成功发出，返回 True。"""
    recorder = _patch_uniseg(monkeypatch)
    result = asyncio.run(message_reaction(_group_event(), "done"))
    assert result is True
    assert recorder.calls == [("148", "mid-1")]


@pytest.mark.parametrize(
    ("status", "expected"),
    [("resolving", "38"), ("done", "148"), ("fail", "10060")],
)
def test_onebot_adapter_uses_numeric_emoji_ids(
    monkeypatch: pytest.MonkeyPatch, status: str, expected: str
) -> None:
    """OneBot 系（onebot11/qq/milky）必须用数字 emoji ID，不能用 Unicode。

    防的 bug：把 🔨 直接发给 set_msg_emoji_like，QQ 会当作非法 emoji_id。
    """
    recorder = _patch_uniseg(monkeypatch, adapter="OneBot V11")
    asyncio.run(message_reaction(_group_event(), status))  # type: ignore[arg-type]
    assert recorder.calls == [(expected, "mid-1")]


@pytest.mark.parametrize(
    ("status", "expected"),
    [("resolving", "🔨"), ("done", "🍼"), ("fail", "❌")],
)
def test_non_onebot_adapter_uses_unicode_emoji(
    monkeypatch: pytest.MonkeyPatch, status: str, expected: str
) -> None:
    """非 OneBot 适配器（如 Telegram）必须用 Unicode 字符分支。

    防的 bug：把数字 "148" 发给 Telegram reaction API。
    """
    recorder = _patch_uniseg(monkeypatch, adapter="Telegram")
    asyncio.run(message_reaction(_group_event(), status))  # type: ignore[arg-type]
    assert recorder.calls == [(expected, "mid-1")]


def test_emoji_map_matches_contract() -> None:
    """EMOJI_MAP 的键与两套取值必须与契约逐字一致。"""
    assert EMOJI_MAP == {
        "resolving": ("38", "🔨"),
        "done": ("148", "🍼"),
        "fail": ("10060", "❌"),
    }


def test_invalid_status_raises_value_error() -> None:
    """非法 status 是调用方编码错误 → ValueError（不是运行时抖动）。

    防的 bug：静默 return False，把「写错状态名」伪装成「平台不支持」。
    """
    with pytest.raises(ValueError):
        asyncio.run(message_reaction(_group_event(), "nope"))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# with_reaction：三态 + 控制流异常判成功
# ---------------------------------------------------------------------------


async def _run_with_reaction(
    handler: Any,
    event: Any,
) -> Any:
    """在设置 current_event 的前提下运行被 with_reaction 包装的 handler。"""
    token = current_event.set(event)
    try:
        return await with_reaction(handler)()
    finally:
        current_event.reset(token)


def test_with_reaction_resolving_then_done_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """进入打 resolving、正常结束打 done，并透传返回值。"""
    recorder = _patch_uniseg(monkeypatch)

    async def handler() -> str:
        await asyncio.sleep(0)
        return "ok"

    result = asyncio.run(_run_with_reaction(handler, _group_event()))
    assert result == "ok"
    assert [emoji for emoji, _ in recorder.calls] == ["38", "148"]


def test_with_reaction_marks_finished_exception_as_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """★关键★ with_reaction 遇到 MatcherException（真实 FinishedException）必须判成功。

    契约最易写错的点：Matcher.finish() 正常结束时会抛 FinishedException
    （MRO: MatcherException → Exception）。天真的 `except Exception: fail`
    会把每一次成功的 finish 都标成 ❌ —— 这一条只在生产才暴露。
    """
    recorder = _patch_uniseg(monkeypatch)

    async def handler() -> None:
        await asyncio.sleep(0)
        raise FinishedException()

    with pytest.raises(FinishedException):
        asyncio.run(_run_with_reaction(handler, _group_event()))
    emojis = [emoji for emoji, _ in recorder.calls]
    assert emojis == ["38", "148"]
    assert EMOJI_MAP["fail"][0] not in emojis


def test_with_reaction_marks_real_exception_as_fail_and_reraises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真正的异常打 fail 并原样上抛（不吞，主流程控制流不被打断）。"""
    recorder = _patch_uniseg(monkeypatch)

    async def handler() -> None:
        await asyncio.sleep(0)
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        asyncio.run(_run_with_reaction(handler, _group_event()))
    assert [emoji for emoji, _ in recorder.calls] == ["38", "10060"]


def test_with_reaction_without_current_event_skips_silently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """current_event 取不到（LookupError）时静默跳过表态，主流程照常执行。"""
    recorder = _Recorder()
    monkeypatch.setattr(uniseg, "message_reaction", recorder.message_reaction)

    async def handler() -> str:
        await asyncio.sleep(0)
        return "ok"

    result = asyncio.run(with_reaction(handler)())
    assert result == "ok"
    assert recorder.calls == []


def test_with_reaction_without_event_still_reraises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """无 current_event 时异常仍必须上抛（跳过表态 ≠ 改变控制流）。"""
    recorder = _Recorder()
    monkeypatch.setattr(uniseg, "message_reaction", recorder.message_reaction)

    async def handler() -> None:
        await asyncio.sleep(0)
        raise FinishedException()

    with pytest.raises(FinishedException):
        asyncio.run(with_reaction(handler)())
    assert recorder.calls == []


# ---------------------------------------------------------------------------
# 纯工具库形态
# ---------------------------------------------------------------------------


def test_plugin_metadata_is_library() -> None:
    """插件必须以 type="library" 的纯工具库形态加载，且导出契约的四项 API。"""
    import nonebot_plugin_message_reaction as pkg

    assert pkg.__plugin_meta__.type == "library"
    assert set(pkg.__all__) == {
        "EMOJI_MAP",
        "ReactionStatus",
        "message_reaction",
        "with_reaction",
    }
