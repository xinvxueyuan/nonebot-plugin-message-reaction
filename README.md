# nonebot-plugin-message-reaction

消息表态（emoji reaction）工具库（抽取自 [zhenxun_bot](https://github.com/zhenxun-org/zhenxun_bot) 的 `nonebot_plugin_parser_lite`）：给其他 NoneBot2 插件提供三态表态（处理中 / 完成 / 失败）的 `message_reaction` API 与 `with_reaction` 装饰器，纯工具库、不带任何指令。

> **qbot 插件** · 宿主仓库：[xinvxueyuan/qbot](https://github.com/xinvxueyuan/qbot)

> **纯工具库形态**：不注册任何指令、不监听事件，只提供 API 供其他 NoneBot 插件 `import` 调用。
> 适配器分派（OneBot `set_msg_emoji_like` / `set_group_reaction`、Telegram reaction 等）交给 [nonebot-plugin-alconna](https://github.com/nonebot/plugin-alconna) 的 `uniseg` 完成，本库不重复实现那张表。
> 表态是锦上添花：任何失败只记 warning + 返回 `False`，绝不影响主流程。

## 功能特性

- 三态表态：`message_reaction(event, status)` 给触发事件的消息打一个 emoji 表态，成功返回 `True`；私聊 / 缺 alconna / 表态失败返回 `False`（绝不抛出）。
- 三态装饰器：`with_reaction` 包 handler —— 进入打 `resolving`（处理中），正常结束打 `done`（完成），异常打 `fail`（失败）后原样上抛。
- 双取值映射：`EMOJI_MAP` 为「状态 → `(OneBot 数字 ID, 其它适配器 Unicode)`」；OneBot 系（onebot11 / qq / milky）用数字 ID，其它适配器用 Unicode。
- 状态字面量：`ReactionStatus = Literal["resolving", "done", "fail"]`。
- 零强制 alconna：alconna 是可选 extra，模块加载时不导入；缺失时 `message_reaction` 记一次 warning 并返回 `False`，`with_reaction` 静默跳过表态。
- 无副作用：插件加载不注册任何 Matcher / Hook，纯库形态可安全 `import`。

### 设计要点

- **私聊直接跳过**：QQ 平台私聊不支持表态，不降级成「另发一条消息说我在处理」。
- **`MatcherException` 判成功**：`finish` / `pause` / `reject` / `skip` 正常结束时会抛异常，
  若当作失败，会把每一次成功都标成 ❌——`with_reaction` 专门把控制流判成 `done` 再上抛。

## 安装

### 依赖

- 运行依赖（以 `pyproject.toml` 的 `dependencies` 为准）：`nonebot2 >= 2.5.0`、`nonebot-adapter-onebot >= 2.4.6`。
- （可选）额外依赖：`nonebot-plugin-alconna >= 0.62.0`（extra `alconna`，跨平台表态能力，推荐）。
- Python：`>= 3.10`。

### pip 安装

```bash
pip install nonebot-plugin-message-reaction            # 核心（无 alconna 时表态降级为 no-op）
pip install 'nonebot-plugin-message-reaction[alconna]'  # 附跨平台表态能力（推荐）
```

### 宿主以 git 子模块引入

```bash
git submodule add -b main https://github.com/xinvxueyuan/nonebot-plugin-message-reaction.git \
  vendor/nonebot-plugin-message-reaction
git -C vendor/nonebot-plugin-message-reaction checkout <钉定的 SHA>
```

- 宿主 `[tool.nonebot] plugin_dirs` 加一行 `vendor/nonebot-plugin-message-reaction/src/plugins`
  （本仓自带的 `plugin_dirs = ["src/plugins"]` 是插件独立开发时用的；仓库实际布局 `src/plugins/nonebot_plugin_message_reaction`）。
- 本仓库为源码权威（`uv` 工程），直接集成时也可把
  `src/plugins/nonebot_plugin_message_reaction/` 拷入目标工程的 plugins 目录。

## 配置

本插件**不读取任何配置项**：源码中没有 `get_plugin_config` / `Config` 模型，也没有 `.env` 键或环境变量前缀，接入后无需任何配置即可工作。与行为相关的只有以下两处，都不是配置项：

- **`EMOJI_MAP` 是模块常量**：`resolving→("38","🔨")`、`done→("148","🍼")`、`fail→("10060","❌")`，见 `src/plugins/nonebot_plugin_message_reaction/reaction.py`；要换 emoji 只能改源码。
- **是否安装 extra `alconna`**：决定能否真正发得出表态（本库自身只做分发调用）；缺失时 `message_reaction` 记一次 warning 并返回 `False`，`with_reaction` 静默跳过，主流程不受影响。

## 使用 / 命令

本插件不注册任何指令，下面的用法都写在**调用方插件**的 handler 里。

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

### API

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

### 与 zhenxun_bot 的对应关系

| 本插件 | zhenxun_bot 来源 |
| --- | --- |
| `EMOJI_MAP` | `nonebot_plugin_parser_lite/constants.py` |
| `message_reaction` | `nonebot_plugin_parser_lite/helper.py` `UniHelper.message_reaction` |
| `with_reaction` | `nonebot_plugin_parser_lite/helper.py` `UniHelper.with_reaction` |

## 开发与测试

首次先装齐依赖组（`pyproject.toml` 的 `[dependency-groups]` 定义了 `dev` 与 `lint`）：

```bash
uv sync --all-groups
```

测试与门禁：

```bash
uv run python -m pytest tests/ -q
uv run ruff check . && uv run ruff format --check .
uv run pyright
```

- `tests/test_smoke.py` 用 fake event + monkeypatch `nonebot_plugin_alconna.uniseg` 覆盖「`message_reaction` 行为」表的每一行与 `with_reaction` 的控制流判定，不连真实 QQ。
- 工具配置：ruff `line-length = 88`、`target-version = "py310"`；pyright `typeCheckingMode = "strict"`、`include = ["src"]`；构建后端 `uv_build`（`module-root = "src/plugins"`）。

## 许可证与相关仓库

- **许可证**：`MIT`（见仓库根目录 `LICENSE` 文件，Copyright (c) 2026 新v学员 (xinvxueyuan)；`pyproject.toml` 的 `license = { text = "MIT" }`）。
- **相关仓库**：
  - [xinvxueyuan/qbot](https://github.com/xinvxueyuan/qbot) —— 宿主，以 `vendor/` 子模块引入本库。
  - [xinvxueyuan/nonebot-plugin-pixiv-novel](https://github.com/xinvxueyuan/nonebot-plugin-pixiv-novel) —— 用 `@with_reaction` / `message_reaction` 给「拉取-发卡片」流程打三态表态。
