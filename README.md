# nonebot-plugin-message-reaction

消息表态（emoji reaction）工具库（抽取自 [zhenxun_bot](https://github.com/zhenxun-org/zhenxun_bot)
`nonebot_plugin_parser_lite` 的 `constants.EMOJI_MAP` 与 `helper.UniHelper.message_reaction` /
`with_reaction`）。**纯工具库形态**：不注册任何指令、不监听事件，
只提供 API 供其他 NoneBot 插件 `import` 调用。

适配器分派（OneBot `set_msg_emoji_like` / `set_group_reaction`、Telegram reaction 等）
交给 [nonebot-plugin-alconna](https://github.com/nonebot/plugin-alconna) 的 `uniseg` 完成，
本库不重复实现那张表。

## 安装

```bash
pip install nonebot-plugin-message-reaction            # 核心（无 alconna 时表态降级为 no-op）
pip install 'nonebot-plugin-message-reaction[alconna]'  # 附跨平台表态能力（推荐）
```

本仓库为源码权威（`uv` 工程），直接集成时也可把
`src/plugins/nonebot_plugin_message_reaction/` 拷入目标工程的 plugins 目录。

## 快速开始

### 三态装饰器（推荐）

```python
from nonebot import on_command
from nonebot.adapters.onebot.v11 import GroupMessageEvent
from nonebot_plugin_message_reaction import with_reaction

matcher = on_command("获取全文")


@matcher.handle()
@with_reaction  # 进入打「处理中」，成功打「完成」，异常打「失败」
async def handle(event: GroupMessageEvent):
    ...
    await matcher.finish("完成")  # finish 抛 FinishedException，会被判为「成功」
```

`with_reaction` 装饰 **handler 函数**（不是 matcher 对象）：

- 进入函数体后第一件事打 `resolving`；
- 正常结束 / `Matcher.finish()` / `pause()` / `reject()` / `skip()`
  （`nonebot.exception.MatcherException` 控制流）→ `done`；
- 其它异常 → `fail`，然后**原样上抛**（绝不吞控制流）；
- `current_event` 取不到时静默跳过表态。

### 直接表态

```python
from nonebot_plugin_message_reaction import message_reaction

ok = await message_reaction(event, "resolving")  # -> bool
```

## API

| 名称 | 说明 |
| --- | --- |
| `ReactionStatus` | `Literal["resolving", "done", "fail"]` |
| `EMOJI_MAP` | 状态 → `(OneBot 数字 ID, 其它适配器 Unicode)`：`resolving→("38","🔨")`、`done→("148","🍼")`、`fail→("10060","❌")` |
| `message_reaction(event, status)` | 给事件消息表态，成功返回 `True`；私聊 / 缺 alconna / 表态失败返回 `False`（绝不抛出） |
| `with_reaction(func)` | 三态表态装饰器 |

### `message_reaction` 行为

| 情形 | 行为 |
| --- | --- |
| 私聊（`event` 无 `group_id`） | 直接返回 `False`，不发、不报错、不降级成额外消息（QQ 平台限制） |
| 缺 alconna | `logger.warning` 一次 + 返回 `False`，绝不抛 |
| 发表态抛任何异常 | `logger.warning` + 返回 `False`，绝不抛（不同实现/权限会静默失败） |
| 成功发出 | 返回 `True` |
| `status` 非法 | `raise ValueError`（调用方编码错误） |

## 设计要点

- **表态是锦上添花**：任何失败都只记 warning + 返回 `False`，绝不影响主流程。
- **私聊直接跳过**：QQ 平台私聊不支持表态，不降级成「另发一条消息说我在处理」。
- **`MatcherException` 判成功**：`finish` / `pause` / `reject` / `skip` 正常结束时会抛异常，
  若当作失败，会把每一次成功都标成 ❌——`with_reaction` 专门把控制流判成 `done` 再上抛。
- **零强制 alconna**：alconna 为可选 extra，模块加载时不导入；缺失时 `message_reaction`
  记一次 warning 并返回 `False`，`with_reaction` 静默跳过。
- **无副作用**：插件加载不注册任何 Matcher / Hook，纯库形态可安全 import。

## 与 zhenxun_bot 的对应关系

| 本插件 | zhenxun_bot 来源 |
| --- | --- |
| `EMOJI_MAP` | `nonebot_plugin_parser_lite/constants.py` |
| `message_reaction` | `nonebot_plugin_parser_lite/helper.py` `UniHelper.message_reaction` |
| `with_reaction` | `nonebot_plugin_parser_lite/helper.py` `UniHelper.with_reaction` |
