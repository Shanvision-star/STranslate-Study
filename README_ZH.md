# STranslate Study

> **本项目起源于 [STranslate](https://github.com/STranslate/STranslate)，是基于上游 v2.0.10 的独立衍生版本。** 原作者为 **zggsong 及 STranslate 贡献者**。翻译、截图、插件框架与 WPF 桌面界面来自上游，本项目在此基础上增加本地词句学习库、勾选汇总打印、脱敏词汇练习和用户自行绑定学习助手。不是上游官方版本，也不代表上游作者、OpenAI 或 Anthropic 提供支持。

保留原始 [MIT LICENSE](LICENSE) 与版权声明。衍生部分同样使用 MIT；第三方运行时、OCR 引擎和模型按各自许可证分发，见 [第三方声明](THIRD_PARTY_NOTICES.md)。**感谢上游作者的工作，请同时支持原项目。**

上游基线：[v2.0.10](https://github.com/STranslate/STranslate/tree/v2.0.10)，提交 `2a75118fe0fabc1135a619f4393eb3a8d936c5cd`。本版本具体改动和验证范围见 [发布说明](docs/study-release.md)。

**界面组件致谢：** [iNKORE.UI.WPF.Modern](https://github.com/iNKORE-NET/UI.WPF.Modern)，作者 **iNKORE Studios and all iNKORE.UI.WPF.Modern contributors**。该组件有自定义许可，要求公开源码并署名，纳入商业产品需另行取得许可；[iNKORE.UI.WPF](https://github.com/iNKORE-NET/UI.WPF) 使用 LGPL-2.1-or-later。详见 [第三方声明及随附源码](THIRD_PARTY_NOTICES.md)，本仓库 MIT 许可不替代这些条款。

## 用来做什么

在 Windows 上选中网页或 PDF 中的文字，按 **Ctrl+Q** 翻译并保存到本地学习库。不能选中的软件菜单可按 **Ctrl+Alt+Shift+S** 框选识别。快捷键可以在设置中更改。

- 保存原文、译文和可获取的公开来源链接；无法可靠获取链接时不编造。来源链接会去掉查询参数和片段。
- 学习库可搜索、按语种/日期筛选、隐藏译文复习。**需要时勾选条目再汇总打印**，不会自动打印全部记录。
- 可选每两天整理一轮实用词汇，用搭配、造句、语法和一问一答练习。候选规则不是 CEFR 等级评测，也不把发送成功当作学习掌握。
- 学习库默认只保存在本机；同步默认关闭。开启后，只向自己选择的学习助手发送筛选后的词汇，练习包不包含原段落、来源标题或链接。

## Windows 快速开始

1. 到 [Releases](https://github.com/Shanvision-star/STranslate-Study/releases) 下载 **STranslate-Study-win-x64.zip**，解压到自己可写的目录。系统要求 Windows 10 2004 及以上 x64 / Windows 11 x64。
2. 运行 `STranslate.exe`。发布包包含 .NET 和 Python 运行时，无需自己配置 Python 环境。
3. 在设置 → 翻译服务中选择服务并启用。**初始翻译服务均关闭**：可启用上游内置 Microsoft 在线翻译，或填入自己的 OpenAI 兼容服务 URL、模型名和密钥。在线服务会接收待翻译文本，与学习库同步开关是两条独立链路。
4. 选中文字按 Ctrl+Q。打开主窗口的 **学习库 / 打印** 查看；没有记录时先完成一次成功翻译。
5. 截图 OCR 使用本机 Tesseract，带英语、西语和简体中文模型。如提示原生 DLL 加载失败，安装 [Microsoft Visual C++ x64 运行库](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist)。本项目不包含该运行库安装器。
6. 要做对话练习，点击 **学习助手**，或双击 `Setup-Study.cmd`，按提示选择自己的助手并授权。不要把整个 `PortableConfig` 上传到 GitHub。

首次版本未进行代码签名。下载时核对 Release 的 SHA256 文件。内网配置见 [公司内网使用](docs/study-intranet.md)。

## 绑定自己的学习助手

| 方式 | 能力与前提 | 定时运行 |
| --- | --- | --- |
| Codex CLI | 使用自己已安装并登录的 CLI，绑定明确的会话 UUID，或明确创建专用学习会话；使用自己的模型配置和额度 | 引导可注册当前 Windows 用户的任务 |
| Claude Code CLI | 使用自己已安装并登录的 CLI，绑定明确 UUID，或创建专用学习会话；本次练习禁用内置工具与 MCP 工具 | 同上 |
| Codex 桌面端 → 学习对话 | 生成绑定指引，由当前桌面客户端查找并确认目标；要求客户端确实提供列出、发送、回读对话和自动化工具 | 通过该客户端创建；不保证每个账号/版本具备能力 |
| ChatGPT 手动导入 | 生成 Markdown 练习包，由自己粘贴进学习对话，粘贴后手动确认 | 可定时生成文件，**不会自动写入 ChatGPT** |

这是使用者自行配置的集成，不是 ChatGPT 通用“写入历史聊天”接口，不读取浏览器登录凭据。Codex CLI 会话不等于 ChatGPT 网页对话。详细步骤、暂停和失败处理见 [学习助手说明](docs/study-assistants.md)。

每天 09:00（电脑本地时区）检查，实际发送间隔为两个日历日。Windows 任务要求用户已登录；电脑关机/应用不可用时不能承诺准点执行。已发送但没有确认的批次停止重试，避免重复消息。

## 数据边界

- 便携数据在 `PortableConfig/`；没有便携目录时使用 `%APPDATA%/STranslate-Study/`。
- `StudyLibrary/study.db`、HTML、CSV、Outbox、回执、配置和日志均为本机私有数据；仓库与安装包不包含作者的学习记录、账号密钥或会话 ID。
- 可在引导中输入应过滤的机构/身份词；只在本机保存匹配指纹。规则过滤与联系人/路径清理不能替代人工检查或公司政策，未知专有词仍可能需要排除。
- 初始条目只允许本地保存；开启同步后新采集的条目才会成为候选。旧条目不会因全局开关自动获得发送权限。
- 调用在线翻译或云端 CLI 会离开本机。严格内网请只用公司批准的模型服务，关闭云学习同步。

## 从源码构建

使用 Windows x64、.NET 10 SDK、Python 3.12+ 和 PowerShell 7。在仓库根目录运行：

```powershell
dotnet restore src/Tests/STranslate.Tests/STranslate.Tests.csproj --configfile NuGet.Study.config
dotnet test src/Tests/STranslate.Tests/STranslate.Tests.csproj --no-restore --filter 'FullyQualifiedName~StudyLibraryTests|FullyQualifiedName~TranslationOperation|FullyQualifiedName~TranslationResultCoordinator|FullyQualifiedName~MouseSelectionServiceTests'
python -m pip install pytest
python -m pytest tests -q
pwsh -File tools/Build-Study.ps1
```

构建下载固定版本的公开依赖并校验 SHA256，不读取个人安装目录或凭据。默认测试不调用真实模型。公共包只含指定的翻译插件和本地 Tesseract OCR；原仓库保留的其他插件源代码不代表随本包分发。

## 贡献与来源

衍生功能问题请提交到本仓库，并先移除词库、日志、密钥及来源身份。不要把本版本的问题直接当成上游缺陷报告。原版功能与文档请参阅 [STranslate](https://github.com/STranslate/STranslate) 和 [上游使用文档](https://stranslate.zggsong.com)。

保留上游源码及提交历史；没有将上游作品标为本项目从零原创。发布包附带原 LICENSE、第三方声明及相应许可文本。
