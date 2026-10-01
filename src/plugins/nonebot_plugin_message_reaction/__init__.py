"""nonebot_plugin_message_reaction —— 消息表态（emoji reaction）工具库。

抽取自 zhenxun_bot ``nonebot_plugin_parser_lite``（``constants.EMOJI_MAP`` 与
``helper.UniHelper.message_reaction`` / ``with_reaction``）。**纯工具库形态**：
不注册任何指令、不监听事件，只导出 API 供其他 NoneBot 插件 ``import`` 调用。

公开 API：
    ReactionStatus: 三态字面量 "resolving" / "done" / "fail"
    EMOJI_MAP:      状态 → (OneBot 数字 ID, 其它适配器 Unicode) 映射
    message_reaction(event, status) -> bool: 表态；私聊 / 缺依赖 / 失败返回 False
    with_reaction(func): 三态表态装饰器；MatcherException 控制流判成功、异常重抛

表态底层的适配器分派交给 ``nonebot-plugin-alconna`` 的 ``uniseg``，本库不重复实现。
"""

from nonebot.plugin import PluginMetadata

from .reaction import EMOJI_MAP, ReactionStatus, message_reaction, with_reaction

__plugin_meta__ = PluginMetadata(
    name="消息表态工具库",
    description=(
        "消息表态（emoji reaction）工具库（抽取自 zhenxun_bot parser_lite）："
        "提供三态表态 message_reaction 与装饰器 with_reaction"
    ),
    usage="作为工具库被其他插件 import 调用，不提供任何指令",
    type="library",
    homepage="https://github.com/xinvxueyuan/nonebot-plugin-message-reaction",
)

__all__ = [
    "EMOJI_MAP",
    "ReactionStatus",
    "message_reaction",
    "with_reaction",
]
