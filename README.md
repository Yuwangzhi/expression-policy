# expression-policy

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**给 Claude Code 和 Codex 的默认表达规范：结论先行、信息充分、少防御性措辞；可随时临时暂停。**

独立本地工具，Python 标准库实现，不需要额外技能、模型调用或 API key。它约束“怎么说”，不改变执行模式、工具权限、模型供应商或项目要求。

## 解决什么问题

模型常把回答写成防御性说明：先堆免责声明，预设读者会误解，用“不是 A，而是 B”“不代表”“不能证明”反复划界，最后再总结一遍。信息被埋在防御里，读者反而更难判断。

本工具把默认写法固定为：

**理解任务 → 起草 → 清理无信息的防御/机械化措辞 → 核对事实和关键边界 → 交付**

- 结论先行，再给依据和条件。
- 删除针对假想质疑的自我辩护、假对比和空泛升华。
- 保留真实的限制、负结果、不确定性和证据边界。
- 保持作者原有声音；正式文本中性，个人文章不强行改成模板。
- 不机械禁词，不为了“有力”而虚构、漏信息或改变否定关系。

完整通用规则见 [rules/expression.md](rules/expression.md)；论文写作、润色和学术翻译另用 [rules/academic-writing.md](rules/academic-writing.md)。设计参考见通用规则末尾来源说明。

## 论文写作与既有技能如何配合

采用“通用表达＋按任务读取的论文附加规则”：普通问答保持轻量；实际写论文时再检查贡献与证据、章节职责、比较口径、归因和双语一致性。论文规则由模型按任务读取，hook 只提供路径，不做关键词触发或自动加载全文。

- 本轮明确的文体、语言、精确格式和编辑范围优先于默认写法；本工具不改变宿主指令层级、安全要求或操作授权。
- 已采用 TJU/Nature 等框架时，沿用其任务路由、章节流程、投稿要求和双语约定；相同检查只做一次，不另启一套润色或模型评审。
- “突出优势”“发布会”等叙事建议始终受证据约束，不得隐去相关负结果、选择性报告或悄悄换比较口径。
- 两层规则共用会话开关；暂停表达规范不撤销项目自身的学术要求。隐藏提示仍继续执行规则。

附加规则针对本工具职责独立编写，不收录 TJU/Nature 的技能正文、章节指南、案例或执行代码；这些技能按原许可单独使用，本工具不依赖其安装。规则分工与场景检查见 [兼容性说明](docs/rule-compatibility.md)。

## 快速开始

要求 Python 3.9+；Claude Code 与/或 Codex 已安装并完成登录。

```bash
git clone https://github.com/Yuwangzhi/expression-policy.git
cd expression-policy
python3 install.py
```

Windows PowerShell：

```powershell
git clone https://github.com/Yuwangzhi/expression-policy.git
cd expression-policy
python -X utf8 install.py
& "$env:USERPROFILE\.local\bin\xpctl.cmd" status --client claude --session test
```

安装后重开已有客户端会话。新会话默认开启；全局规则在 hook 未加载时仍然生效，程序化的单轮复位和界面提示需要客户端实际加载 hooks。若终端找不到 `xpctl`，使用 `~/.local/bin/xpctl`（Windows：`%USERPROFILE%\.local\bin\xpctl.cmd`）或把该目录加入 `PATH`。

## 在对话里控制

把命令放在消息开头，可接逗号、句号、分号或换行，再接本轮任务：

| 指令 | 效果 |
| --- | --- |
| `本轮暂停表达规范` | 仅当前轮次暂停；下次真实用户输入恢复会话原状态 |
| `暂停表达规范` | 当前会话持续暂停 |
| `恢复表达规范` | 当前会话恢复开启 |
| `隐藏表达提示` | 关闭状态提示，规则继续执行 |
| `显示表达提示` | 恢复状态提示 |

示例：

```text
本轮暂停表达规范，逐字输出下面的原文。
```

状态按**机器、客户端、会话**隔离。另一个窗口、另一个客户端或另一台机器不会跟着暂停；新会话默认开启。引用、代码块、假设句，以及通知/插件消息中的同名文字不会切换状态。

默认输入 hook 显示 `表达规范 · 输入 · 开启`，并向模型注入当前规则或暂停状态；自由文本回复使用 `【表达规范：开启】`，结束 hook 显示输出状态。纯 JSON、CSV、代码或原文直出不加正文标记。标记说明开关状态，不代表完成了独立语义评审。

命令行：

```bash
xpctl status --client claude --session SESSION_ID
xpctl off --client claude --session SESSION_ID
xpctl on --client claude --session SESSION_ID
xpctl once --client codex --session SESSION_ID
xpctl quiet --client claude --session SESSION_ID
xpctl loud --client claude --session SESSION_ID
```

省略 `--session` 时读取 `CLAUDE_SESSION_ID` / `CODEX_THREAD_ID`；缺少真实 ID 会报错，不退化成全局开关。暂停只撤销表达风格和编辑流程，保留真实性、安全、权限、任务要求和用户指定格式。

## 安装内容

```text
~/.local/bin/xpctl                            启动器（Windows: xpctl.cmd）
~/.local/share/expression-policy/             运行文件与内置规则
~/.config/expression-policy/rules.md          通用规则；升级更新未定制副本
~/.config/expression-policy/academic-writing.md  论文附加规则；按任务读取
~/.config/expression-policy/CONTROL.md        使用与维护说明
~/.local/state/expression-policy/sessions/    按会话隔离的开关，不保存消息正文
~/.local/state/expression-policy/backups/     安装备份与 manifest
~/.claude/settings.json                       SessionStart/UserPromptSubmit/Stop command hooks
~/.claude/CLAUDE.md                           带 expression-policy 标记的管理段
~/.codex/hooks.json                           SessionStart/UserPromptSubmit/Stop lifecycle hooks
~/.codex/AGENTS.md                            带 expression-policy 标记的管理段
```

安装器增量修改：只替换自己的处理器和标记段，保留其他 hooks、设置、插件和全局指令。运行文件用临时文件原子替换；失败时按 manifest 回退。

## Codex hook 信任

Codex 需要支持本地 lifecycle hooks。安装器**不修改 `config.toml` 信任状态、不设置全局 bypass、不启动模型**。首次安装或 hook 命令变化后，在 Codex `/hooks` 中审阅三条本地命令并信任。

也可以审阅脚本后显式使用本地管理工具：

```bash
python3 ~/.local/share/expression-policy/codex_hook_admin.py --codex codex
python3 ~/.local/share/expression-policy/codex_hook_admin.py --codex codex --approve
python3 ~/.local/share/expression-policy/codex_hook_admin.py --codex codex
```

Windows：

```powershell
python -X utf8 "$env:USERPROFILE\.local\share\expression-policy\codex_hook_admin.py" --codex codex
python -X utf8 "$env:USERPROFILE\.local\share\expression-policy\codex_hook_admin.py" --codex codex --approve
```

工具通过本机 `app-server` 的 `hooks/list` 读取原生哈希，再用 `config/batchWrite` **只批准这三条表达 hook**。它拒绝插件来源、其他配置、复合 shell 命令、缺失/重复事件及不匹配的 key/hash；不推算哈希、不批准其他 hook、不调用模型。已有 `notify`、模型、凭据和其他信任记录保留。可用 `--codex-home PATH` 指向自定义配置目录。

## 与 Claude–Codex Loop 同时安装

两者互不接管，可同时使用：

| 项目 | expression-policy | CCL |
| --- | --- | --- |
| 全局标记 | `expression-policy` | `claude-codex-loop` |
| 运行目录 | `~/.local/share/expression-policy` | `~/.local/share/claude-codex-loop` |
| 状态目录 | `~/.local/state/expression-policy` | `~/.local/state/claude-codex-loop` |
| Claude hooks | 指向 `expression_policy.py` 的 command hooks | 自己的 command/module hooks |
| Codex hooks | `~/.codex/hooks.json` 三条表达处理器 | 不安装 Codex hooks |

Claude Code 会在同一事件上执行两套 hooks：CCL 提供模式状态，本工具提供表达状态；各自输出提示，不共享状态。任一方的安装/升级/卸载只处理自己的处理器和标记。本工具不导入 CCL，CCL 也不需要引用本工具。

CCL 的 Codex worker 读取 `~/.codex/AGENTS.md` 中的默认表达管理段；交互式会话的临时暂停不会自动传给 worker，这是会话隔离的结果。需要在 worker 中暂停时，在任务提示或任务约束中写明。

## 自定义、升级与卸载

- 自定义 `~/.config/expression-policy/rules.md` 或 `academic-writing.md`。升级前与上次内置副本逐字节比较：完全一致才更新；自定义或来源未知的文件保留。安装结果 `rules_updated` 逐文件报告处理状态；新版默认副本在 `~/.local/share/expression-policy/rules/`。
- 升级：拉取新版本后重新运行 `install.py`，检查处理状态，再在新会话验证 hook。被保留的自定义规则需要比较后选择性合并；安装器不改其他工具或个人指令中的旧写作规则。
- 卸载：`python3 install.py --uninstall` 移除 hooks、管理段、运行文件，保留规则和会话状态；加 `--purge` 一并移除。
- 手动恢复：安装备份在 `~/.local/state/expression-policy/backups/`，先比较当前文件，避免覆盖之后的新改动。

## 开发与验证

```bash
python3 -X utf8 -m unittest discover -s tests -v
```

测试不需要模型登录，不发付费模型请求。覆盖会话/客户端隔离、一次性暂停、重复投递、非用户输入、结构化输出提示、安装幂等、保留自定义内容、失败回退、与 CCL 共存的 hooks 保留，以及有限范围的 Codex 信任写入。部署后仍需在新会话检查真实 hook 活动；配置生成和离线测试不等于客户端已热加载，也不等于生成质量评测。

## 边界

- 规则约束表达，不替代事实核查、代码测试、安全审查或项目规范。
- 不承诺规避 AI 检测，不虚构个人经历、引用或数据。
- 默认规则参考 Grice 合作原则、ASD-STE100 清晰表达思路及公开的 Humanizer / anti-defensive-writing 方法，独立整理；不打包或运行这些第三方技能，也不宣称符合完整 ASD-STE100 英文标准。
- 客户端是否显示 hook 提示由客户端决定；不要把“已注入”说成“已人工验收”。

## 参考

- [Codex hooks](https://learn.chatgpt.com/docs/hooks)
- [Claude Code hooks](https://code.claude.com/docs/en/hooks)

[MIT License](LICENSE)。
