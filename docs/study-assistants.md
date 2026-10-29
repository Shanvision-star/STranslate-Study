# 绑定自己的学习助手

首次先运行一次成功翻译，再点击主窗口“学习助手”或双击发布包根目录 `Setup-Study.cmd`。每位用户使用自己的登录、模型配置、账户额度、会话 ID。默认发送关闭；引导明确同意后才启用。英文和西语可分别运行引导绑定，新增过滤词会合并保留旧规则。

## 1. Codex CLI / Claude Code

安装并正常登录对应官方 CLI。这里调用本机可执行文件，不收集登录令牌。Windows 建议使用官方原生安装器；若 PATH 找不到，填写实际 `.exe` 路径。

选择 Codex CLI 或 Claude Code，输入专用学习会话 UUID。留空表示在本次引导中允许新建专用学习会话，创建成功后保存返回的 ID；不会使用“最近一个会话”。已有会话填其原工作目录；新会话默认独立 `AssistantWorkspace`，不把整个学习库用作模型工作目录。

确认启用后可选择“现在生成一轮”和“创建定时任务”。Codex 使用 `exec` 的只读沙箱；Claude Code 使用 `-p`，禁用内置工具与 MCP 工具。不添加绕过权限的参数。会话自身历史和用户已有 CLI 配置仍由相应客户端管理，因此建议绑定专门的语言练习会话。

一次自动练习从明确的通用词表中选最多 5 个新词；存在旧词时最多 3 新词 + 2 复习词。未知候选仅供本机检查，本版不会自动发送。词表位于 `StudyTools/study_practice.py` 的 `PREFERRED`，不宣称覆盖所有高级词或提供正式难度评级。

官方行为参考：[Codex 非交互执行](https://developers.openai.com/codex/noninteractive)、[Claude Code CLI](https://code.claude.com/docs/en/cli-reference)。CLI 正常结束和包含词汇的回执只记录为 `cli_completed`，不等于在某个桌面窗口中回读验证。

## 2. Codex 桌面端绑定自己的 ChatGPT 学习对话

引导选第三项，会生成并打开 `PortableConfig/StudyLibrary/bind-desktop.txt`。把内容粘贴到自己的 Codex 桌面会话。该指引要求客户端：

1. 检查是否实际提供 `list_threads`、`send_message_to_thread`、`read_thread` 和 `automation_update`。
2. 列出用户自己的学习对话，确认语种与目标，取得用户启用发送及定时任务的授权。
3. 调用 `study_bridge.py bind --provider codex_desktop --session-id <自己的UUID> --language en --enable --app-dir <应用目录>` 保存绑定。西语使用 `es`。
4. 用 `study_practice.py candidates` 获取无来源候选，选择允许词汇，`prepare` 后先 `claim`，成功才使用客户端工具发送。
5. `read_thread` 回读批次和全部词汇，再 `ack`；不能把队列接收当作远端已保存。
6. 创建当前客户端的定时任务，每天 09:00 检查 `status.next_due`，实际每两个日历日处理一次。没有到期或没有新信息时保持安静。

外部客户端改写设置后，请退出并重新打开 STranslate Study，让正在运行的窗口重新读取开关；否则旧设置可能覆盖新配置。若由主窗口“学习助手”引导直接配置 CLI，它会在引导结束后刷新开关。

**工具不可用时必须降级为手动模式。** ChatGPT API 的生成能力不等于向个人网页历史对话写入内容的通用接口；本项目不使用浏览器 Cookie 或私有接口。桌面自动化不要同时另注册 Windows CLI 任务。

`prepare` 的参数示例结构（实际文件留在本机，不提交仓库）：

```json
{"en":{"thread_id":"用户确认的目标UUID"}}
```

```json
{"language":"en","terms":["coherent","mechanism"],"review_terms":[],"grammar_focus":"relative_clauses"}
```

可用语法值由 `candidates` 返回。命令参数可用发布包 `python/python.exe -X utf8 StudyTools/study_practice.py --help` 查看。

## 3. ChatGPT 手动模式

选择第四项并确认启用素材生成。`Run-Study.cmd` 或定时任务会在 `PortableConfig/StudyLibrary/Outbox/` 生成 Markdown。自己查看内容后复制进学习对话；没有自动网络发送。

粘贴后在应用目录运行（用实际批次替换占位文字）：

```powershell
.\python\python.exe -X utf8 .\StudyTools\study_bridge.py confirm-manual --batch <批次ID> --confirm --app-dir .
```

只标记 `manual_confirmed`，与远端工具回读 `verified` 区分。未确认的素材不会被当成已学习或重复生成新一轮。

## 检查、停用和失败恢复

```powershell
.\python\python.exe -X utf8 .\StudyTools\study_bridge.py doctor --app-dir .
```

- `disabled`：未启用；`waiting_for_first_capture`：没有词库；`no_candidates`：无可用词汇。先明确选英语或西语再翻译；自动语言无法确认时使用主窗口语种确认入口。
- 默认本地记录不会在开关启用时自动升级为可发送，同一条目重复翻译也保留原来的本地限制。先启用学习助手，再采集新的词句查看候选；本预览版尚未提供旧条目批量改权限的入口。
- `not_due`：未到两日间隔；`exported_only`：文件已生成，未发送。
- `dispatching` / `needs_attention` / `needs_verification`：可能已发出，先到目标会话核对，不要盲目重发。确认送达后可以明确手动确认；没有可靠证据时保持待核对。
- 只有未开始发送的 `prepared` 批次可用 `cancel --batch <ID> --confirm` 取消；当天相同批次不会自动复活。停止今后任务请重新运行设置选择不启用，或关闭软件“学习库同步”开关。
- `Disable-StudyTask.ps1` 或 `study_bridge.py uninstall-task --confirm --app-dir .` 移除本应用注册的 Windows 任务，保留学习数据。客户端自动化需要在相应客户端停用。
- Windows 任务以当前用户登录身份运行，无管理员提权。无需把口令写入任务；移动应用目录后应先删除旧任务，再重新注册。

练习批次的交付状态不是掌握程度；教学一次只问一个问题，等用户回答后再纠错。
