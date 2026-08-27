# Windows 第一次对话

把下面整段作为 Windows Codex 新窗口的第一条消息：

```text
请把这个 Codex 窗口安装成“发送本人有权处理的视频链接即可导出 MP3”的工具：

https://github.com/delu543/weixin-replay-to-mp3

请直接完成安装和验证，不要只列出缺少 Python、FFmpeg 或 Git。只在 Windows 原生
PowerShell 中运行，不要把 WSL/Linux 的 unsupported_platform 当成 Windows 结果。

先读取 main 的 AGENTS.md、README.md 和 docs/WINDOWS_INSTALL.md。然后执行：

1. 如果 Codex 提供工作区依赖查询工具，先取得它返回的 Windows bundled Python 精确
   路径；不要猜路径，也不要输出其他环境信息。
2. 有本地 checkout 时运行 bootstrap-windows.ps1，并把 bundled Python 路径通过
   -PythonExecutable 传入。
3. 没有 checkout，或 Git/raw GitHub/jsDelivr 在 PowerShell 中失败时，不要停止。按
   docs/WINDOWS_INSTALL.md 依次使用 GitHub API、Git blob、Release Asset、codeload、
   三个 jsDelivr 和 bundled Python 下载器。每个候选必须匹配文档中的固定字节数和
   SHA-256 后才能执行。
4. 如果终端下载失败但内置浏览器能读取仓库，不要让我手工放文件：用浏览器完整读取
   小型 bootstrap-windows.ps1，精确写入本地并按文档哈希验证；如果浏览器能保存固定
   标签安装器或 ZIP，则把该文件交给 bootstrap-windows.ps1 -LocalArtifact。
5. 我授权在当前 Windows 用户范围内安装这个工具所需的 Python、私有 FFmpeg、yt-dlp、
   EJS 和 Deno；不得修改系统代理、安装证书、读取浏览器 Cookie/账号 Token、读取微信
   聊天或联系人数据库，也不得操作其他 Windows 用户的数据。
6. 某条下载路径失败后继续下一条，但不要无上限重试。只有 GitHub API + bundled
   Python、Git blob、Release Asset、codeload、jsDelivr 和本地浏览器文件都失败，才能
   报告阻塞；报告必须列出每个 transport/client 的实际错误。
7. 安装命令退出码为 0、status 为 ready、doctor/preflight 通过，并出现
   “READY: you can send a link now”后，才算完成。

完成后只需告诉我：安装版本、doctor/preflight 结果、MP3 输出目录，并说
“已经可以发送链接”。以后我发送 YouTube、X/Twitter、小红书、视频号、直接媒体或
其他支持网页链接时，目标是导出完整校验的 MP3，不生成文字稿。

Windows 视频号只有在工具明确返回 Manual playback is required 时，才让我在标题恰好
为“文件传输助手”的聊天中手动发送、打开最新同一链接并开始播放。不得盲点或向其他
聊天发送消息；收到我的精确播放确认后再继续。
```
