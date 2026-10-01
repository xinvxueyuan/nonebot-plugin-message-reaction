"""消息表态（emoji reaction）三态反馈工具（alconna 可选依赖）。

移植自 zhenxun_bot ``nonebot_plugin_parser_lite``：

- ``constants.py`` 的 ``EMOJI_MAP``（状态 → OneBot 数字 ID / Unicode 两套取值）；
- ``helper.py`` 的 ``UniHelper.message_reaction``（私聊跳过 + 全异常容错）与
  ``UniHelper.with_reaction``（三态装饰器）。

本模块在加载时不导入 ``nonebot-plugin-alconna``（保持 alconna 为可选依赖），
仅在调用时懒加载并检查：未安装时 :func:`message_reaction` 记录一次 warning 并
返回 ``False``（绝不抛出），:func:`with_reaction` 则静默跳过表态、主流程不受影响。

表态底层的适配器分派（``set_msg_emoji_like`` / ``set_group_reaction`` 等）交由
alconna 的 ``uniseg`` 完成，本库不重复实现那张分派表。
"""

from __future__ import annotations

from functools import wraps
import importlib.util
import logging
from typing import TYPE_CHECKING, Any, Final, Literal

from nonebot.exception import MatcherException
from nonebot.matcher import current_event

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from nonebot.adapters import Event

logger = logging.getLogger("nonebot_plugin_message_reaction")

__all__ = [
    "EMOJI_MAP",
    "ReactionStatus",
    "message_reaction",
    "with_reaction",
]

ReactionStatus = Literal["resolving", "done", "fail"]

#: 状态 → (OneBot 系数字 ID, 其它适配器 Unicode)
EMOJI_MAP: Final[dict[str, tuple[str, str]]] = {
    "resolving": ("38", "🔨"),
    "done": ("148", "🍼"),
    "fail": ("10060", "❌"),
}

_ALCONNA_NOT_INSTALLED_MSG = (
    "使用消息表态功能需要安装 nonebot-plugin-alconna："
    "pip install 'nonebot-plugin-message-reaction[alconna]'"
)

_REACTION_FAILED_MSG = "消息表态失败（当前实现或权限可能不支持），已忽略，不影响主流程"

_INVALID_STATUS_FMT = "非法的 ReactionStatus: {!r}"


def _require_alconna() -> Any:
    """返回 alconna 的 ``uniseg`` 模块；未安装则抛出带安装指引的 ImportError。"""
    if importlib.util.find_spec("nonebot_plugin_alconna") is None:
        raise ImportError(_ALCONNA_NOT_INSTALLED_MSG)
    from nonebot_plugin_alconna import uniseg

    return uniseg


def _is_private(event: Event) -> bool:
    """判断事件是否为私聊。

    优先使用 alconna 的 ``get_target(event).private``（跨平台权威判定）；alconna
    未安装或当前无 Bot 上下文（``get_target`` 抛错）时，退化为「事件没有
    ``group_id``」——这正对应契约里「私聊（event 无 group_id）」的定义。
    QQ 平台私聊不支持表态，必须直接跳过。
    """
    try:
        uniseg = _require_alconna()
        return bool(uniseg.get_target(event).private)
    except Exception:
        return getattr(event, "group_id", None) is None


async def message_reaction(event: Event, status: ReactionStatus) -> bool:
    r"""给触发事件的消息添加一个表态（emoji reaction）。

    适配器取值走 :data:`EMOJI_MAP`：OneBot 系（onebot11 / qq / milky）用数字
    emoji ID，其它适配器用 Unicode 字符。私聊、缺少 alconna、发表态失败都只
    返回 ``False``，绝不抛出、绝不降级成额外消息，保证表态不影响主流程。

    Args:
        event: 触发事件（NoneBot Event）。
        status: 三态之一 ``"resolving"`` / ``"done"`` / ``"fail"``。

    Returns:
        成功发出返回 ``True``；私聊、缺少 alconna 或发表态失败返回 ``False``。

    Raises:
        ValueError: ``status`` 不是 ``ReactionStatus`` 的合法取值（调用方写错）。
    """
    if status not in EMOJI_MAP:
        raise ValueError(_INVALID_STATUS_FMT.format(status))

    # 私聊不支持表态（QQ 平台限制）：直接跳过，不发、不报错、不降级成额外消息。
    if _is_private(event):
        return False

    try:
        uniseg = _require_alconna()
    except ImportError:
        logger.warning(_ALCONNA_NOT_INSTALLED_MSG)
        return False

    try:
        message_id = uniseg.get_message_id(event)
        on_onebot = uniseg.get_target(event).adapter in (
            uniseg.SupportAdapter.onebot11,
            uniseg.SupportAdapter.qq,
            uniseg.SupportAdapter.milky,
        )
        emoji = EMOJI_MAP[status][0] if on_onebot else EMOJI_MAP[status][1]
        await uniseg.message_reaction(emoji, message_id=message_id)
    except Exception:
        logger.warning(_REACTION_FAILED_MSG)
        return False
    return True


def with_reaction(
    func: Callable[..., Awaitable[Any]],
) -> Callable[..., Awaitable[Any]]:
    r"""为 handler 包上三态表态（处理中 → 完成 / 失败）的装饰器。

    进入函数体后第一件事打 ``resolving``；正常结束打 ``done``；
    ``nonebot.exception.MatcherException``（``finish`` / ``pause`` / ``reject`` /
    ``skip`` 等 NoneBot 控制流异常）同样判为「成功」打 ``done`` —— 天真地把它
    当普通异常会**把每一次正常 finish 都标成 ❌**，这是本装饰器最关键的一条；
    其它异常才打 ``fail``。两类异常都原样上抛，绝不吞掉 NoneBot 的控制流。

    事件从 ``nonebot.matcher.current_event`` 取，取不到（``LookupError``）时
    静默跳过表态，主流程照常执行。

    Args:
        func: 被装饰的异步 handler 函数。

    Returns:
        包装后的异步函数。
    """

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            event: Any = current_event.get()
        except LookupError:
            event = None

        if event is not None:
            await message_reaction(event, "resolving")

        try:
            result = await func(*args, **kwargs)
        except MatcherException:  # NoneBot 控制流，不是失败
            if event is not None:
                await message_reaction(event, "done")
            raise
        except Exception:  # 真正的失败
            if event is not None:
                await message_reaction(event, "fail")
            raise
        else:
            if event is not None:
                await message_reaction(event, "done")
            return result

    return wrapper
