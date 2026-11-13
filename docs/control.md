# 默认表达规范与会话控制

`expression-policy` 为 Claude Code 与 Codex 提供同一套默认表达原则。它是独立工具：不安装 Humanizer 或其他编辑技能，不调用模型，不接管 Claude–Codex Loop（CCL）或其他插件的状态。

## 默认工作方式

每次回答按 **理解任务 → 起草 → 清理无信息的防御/机械化措辞 → 核对事实和关键边界 → 交付** 执行。结论先行，信息充分而不重复；保留不确定性、负结果、作者声音和用户要求的文体。短问答轻量执行，长文章逐段执行。

完整规则见 [rules/expression.md](../rules/expression.md)。这是一份独立整理的规则，不声称调用了引用的第三方技能或符合完整 ASD-STE100 英文标准。项目原有的学术、代码、格式、安全要求和权限继续有效；表达规则不扩大工具权限，也不改变执行模式。

## 输入、输出与临时开关

将以下命令直接放在消息开头，可接中文/英文逗号、句号、分号或换行及本轮任务：

| 指令 | 效果 |
| --- | --- |
| `本轮暂停表达规范` | 仅当前输入轮次暂停；下次真实用户输入恢复会话原状态 |
| `暂停表达规范` | 当前会话持续暂停 |
| `恢复表达规范` | 当前会话恢复开启 |
| `隐藏表达提示` | 关闭状态提示，保留规则 |
| `显示表达提示` | 恢复状态提示 |

临时状态按机器、客户端和 session 隔离。新 session 默认开启，另一窗口、另一台机器或另一插件不会跟着暂停。引用、代码块、假设句，以及标记为通知/插件的输入不会切换状态。相同 Codex `turn_id` 重投递不会提前消耗一次性暂停。

示例：`本轮暂停表达规范，逐字输出下面的原文。`

默认输入 hook 显示 `表达规范 · 输入 · 开启`，并向模型提供状态；回复按规则使用 `【表达规范：开启】`；结束 hook 显示输出状态。纯 JSON、CSV、代码或原文直出不加正文标记。界面是否显示提示由客户端决定；**标记说明开关状态，不代表完成了独立语义评审**。Stop 不强制续跑，不因措辞检查阻塞结束。

命令行入口：

```bash
xpctl status --client claude --session SESSION_ID
xpctl off --client claude --session SESSION_ID
xpctl on --client claude --session SESSION_ID
xpctl once --client codex --session SESSION_ID
xpctl quiet --client claude --session SESSION_ID
xpctl loud --client claude --session SESSION_ID
xpctl render --client claude --session SESSION_ID
```

`once` 命令行开关供下一次输入 hook 使用；自然语言的“本轮暂停”作用于当前输入。省略 `--session` 时分别读取 `CLAUDE_SESSION_ID` / `CODEX_THREAD_ID`，缺少真实 ID 就报错，不退化成全局开关。暂停只撤销这组表达流程，不撤销真实性或其他任务要求。

## 安装、加载与卸载

```bash
git clone https://github.com/Yuwangzhi/expression-policy.git
cd expression-policy
python3 install.py
# Windows: python -X utf8 install.py
```

安装器会：

- 安装运行文件到 `~/.local/share/expression-policy`，创建 `~/.local/bin/xpctl`（Windows 为 `xpctl.cmd`）。
- 首次建立 `~/.config/expression-policy/rules.md`；后续保留已有自定义规则。
- 在 Claude `~/.claude/CLAUDE.md` 与 Codex `~/.codex/AGENTS.md` 中添加独立的 `expression-policy` 管理段；保留既有管理段和其他个人指令。
- 向 `~/.claude/settings.json` 与 `~/.codex/hooks.json` 增量注册 `SessionStart`、`UserPromptSubmit`、`Stop`；只替换本工具自己的处理器，保留其他组和索引。
- 备份所有改动目标，失败时回退。

重开已有客户端会话以加载新 hooks。全局指令即使在 hook 未加载时仍提供默认写作要求；程序化的单轮复位和界面事件提示需要实际加载 hook。首次 `SessionStart` 和首轮输入注入完整规则，随后注入短流程、当前状态、规则位置和摘要哈希。若 `xpctl` 不在 `PATH`，使用 `~/.local/bin/xpctl`（Windows：`%USERPROFILE%\.local\bin\xpctl.cmd`）。

卸载：

```bash
xpctl --help  # 或直接阅读安装器
python3 install.py --uninstall          # 移除 hooks、管理段、运行文件；保留规则和会话状态
python3 install.py --uninstall --purge  # 连同规则与状态一并移除
```

卸载只删除指向本工具 `expression_policy.py` 的处理器和 `expression-policy` 管理段，不删除 CCL 或其他插件的 hooks、配置、设置或插件目录。

## Codex hook 信任

Codex 必须支持本地 lifecycle hooks。安装器**不修改 `config.toml` 信任状态、不设置全局 bypass、不启动模型**。首次安装或 hook 命令变化后，在 Codex `/hooks` 中审阅这三条本地命令并信任。

也可在审阅脚本后明确使用本地管理工具：

```bash
python3 ~/.local/share/expression-policy/codex_hook_admin.py --codex codex
python3 ~/.local/share/expression-policy/codex_hook_admin.py --codex codex --approve
python3 ~/.local/share/expression-policy/codex_hook_admin.py --codex codex
```

Windows：

```powershell
python -X utf8 "$env:USERPROFILE/.local/share/expression-policy/codex_hook_admin.py" --codex codex
python -X utf8 "$env:USERPROFILE/.local/share/expression-policy/codex_hook_admin.py" --codex codex --approve
```

可用 `--codex-home PATH` 指向自定义 Codex 配置目录。工具通过本机 `app-server` 的 `hooks/list` 读取原生哈希，再用 `config/batchWrite` **仅批准这三条表达 hook**。它拒绝插件来源、其他配置、复合 shell 命令、缺失/重复事件及不匹配的 key/hash；不推算哈希、不批准其他 hook、不调用 `thread/start` 或 `turn/start`。已有 `notify`、模型、凭据和其他信任记录保留。

## 与 Claude–Codex Loop 同时安装

两者可以同时安装，互不接管：

| 项目 | 本工具 | CCL |
| --- | --- | --- |
| 全局标记 | `expression-policy` | `claude-codex-loop` |
| 运行目录 | `~/.local/share/expression-policy` | `~/.local/share/claude-codex-loop` |
| 状态目录 | `~/.local/state/expression-policy` | `~/.local/state/claude-codex-loop` |
| Claude hooks | 指向 `expression_policy.py` 的 command hooks | 自己的 command 或 module hooks |
| Codex hooks | `~/.codex/hooks.json` 中三条表达处理器 | 不安装 Codex hooks |

重装或升级任一方只处理自己的处理器和标记。Claude Code 会在同一事件上执行两套 hooks：CCL 提供模式状态，本工具提供表达状态；两者各自输出提示，不共享状态。CCL 的 installer 只识别 `ccl` 启动器，本工具的 installer 只识别 `expression_policy.py` 和旧原型 `claude-codex-loop/expression.py`。不需要在 CCL 中引入表达模块，也不需要在表达工具中调用 CCL。

CCL 的 Codex worker 会读取 `~/.codex/AGENTS.md` 中的默认表达管理段；交互式会话的临时暂停不会自动传给 worker，这是独立会话隔离的结果。需要在 worker 中暂停时，在任务提示或 CCL 任务约束中写明。

## 定制、升级与恢复

- 自定义 `~/.config/expression-policy/rules.md`；安装器不会覆盖。新版默认副本在 `~/.local/share/expression-policy/rules/expression.md`，可比较后选择更新。
- `~/.config/expression-policy/CONTROL.md` 是随版本更新的使用说明；旧版在安装备份内。
- 状态位于 `~/.local/state/expression-policy/sessions/`，不保存输入正文。`EXPRESSION_STATE_DIR` / `EXPRESSION_CONFIG_DIR` 可覆盖运行时目录。
- 安装备份位于 `~/.local/state/expression-policy/backups/`，manifest 包含规则、hooks 和程序文件。恢复某次备份时先比较当前文件，避免覆盖之后的新改动。
- 不要把个人 `CLAUDE.md`、`AGENTS.md`、settings/config、备份或会话状态提交到 Git。

## 验证范围

自动测试覆盖 session/client 隔离、一次性暂停、重复投递、非用户输入、结构化输出约束、安装幂等、保留自定义内容、失败回退、有限范围的 Codex 信任写入，以及与 CCL 同时安装的共存。Python 测试不需要模型登录，不发付费模型请求。部署到某个客户端后仍需在新会话检查真实 hook 活动；单纯生成配置或通过离线测试不代表客户端已热加载，也不等于生成质量的对照评测。

接口依据：[Codex hooks](https://learn.chatgpt.com/docs/hooks)、[Claude hooks](https://code.claude.com/docs/en/hooks)。
