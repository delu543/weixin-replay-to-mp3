# 视频号链接转 MP3（Codex 工具）

把一个本人有权访问的视频号链接交给 Codex，下载并验证完整媒体，最后导出 MP3。

- macOS：通过受保护的 `文件传输助手`自动链路定位、发送/复用链接并打开播放。
- Windows：复用同一套下载、断点续传、转码和校验核心；没有可靠微信界面适配时，
  由用户完成一次明确的发送、打开和播放。

使用界面就是一个 Codex 对话窗口，不需要另外学习命令行。

## 最简单的使用方式

第一次，在 Codex 中发送：

```text
请读取 https://github.com/delu543/weixin-replay-to-mp3，按仓库说明安装并检查。
以后我在本窗口发送视频号链接时，直接帮我导出成 MP3。
```

安装检查通过后，日常只需要发送：

```text
https://weixin.qq.com/sph/<视频短链接 ID>
```

Codex 会返回最终文件路径、大小和时长。默认文件位于当前系统账户的 Downloads 目录：

```text
Downloads/WeixinReplayMP3/<本地隔离命名空间>/weixin_<短链接 ID>.mp3
```

同一链接再次发送时会先完整解码验证现有 MP3；通过就直接复用，不会再次操作微信、
重复下载或二次转码。中途断开时，也只会继续当前用户命名空间内、与目标短链接绑定的
抓取和分片下载状态。

## macOS 与 Windows 的差异

| 系统 | 微信入口 | 后续处理 |
| --- | --- | --- |
| macOS | 自动验证 `文件传输助手`、发送或复用链接、打开并证明播放 | 完整接入下载、断点续传、解密、转 MP3、完整解码 |
| Windows | 先自动尝试不需要微信界面的目标绑定来源；需要微信时由用户手动发送、打开并确认播放 | 与 macOS 共用同一套下载、断点续传、解密、转 MP3、完整解码 |
| Linux/云端 | 不支持本机微信入口 | 不宣称支持本机微信操作 |

两端都需要：

- Python 3.9 或更高版本；
- 官方桌面微信已登录；
- 足够空间保存原视频工作文件和最终 MP3。

只有 macOS 自动微信界面链路需要 Swift Command Line Tools 和辅助功能权限。

Windows 当前不会盲点微信界面，也不会自动向任何聊天发送消息。如果命令返回
`Manual playback is required`，Codex 必须告诉用户并等待完成以下步骤：

1. 打开官方 Windows 微信。
2. 打开标题恰好为 `文件传输助手` 的聊天。
3. 把本次链接发进去，打开最新的同一链接并开始播放；不要同时播放其他微信视频。
4. 回到 Codex 明确回复“这个链接已经开始播放”。

确认前不会扫描近期运行文件。确认后，工具只检查已知的安全播放/运行目录，再继续同一
下载和转码核心。如果 Windows 微信版本把播放运行文件放在其他位置，可以显式设置
`WEIXIN_REPLAY_RUNTIME_ROOTS`，多个目录用分号分隔；不得把它指向聊天或联系人数据库。

## 用户数据隔离

项目没有共享服务器，也不会把运行数据写回 GitHub。默认隔离键由当前操作系统账户、
本机 Home 目录和可选本地 profile 共同生成；目录名只包含短哈希，不直接包含用户名或
profile 名。

macOS：

```text
~/Library/Application Support/WeixinReplayToMP3/data/profiles/<隔离命名空间>/
~/Downloads/WeixinReplayMP3/<隔离命名空间>/
```

Windows：

```text
%LOCALAPPDATA%\WeixinReplayToMP3\data\profiles\<隔离命名空间>\
%USERPROFILE%\Downloads\WeixinReplayMP3\<隔离命名空间>\
```

- 不同电脑、不同系统账户默认不会共享状态、分片、解密材料或 MP3；
- 直接从 GitHub 检出的源码运行，也不会把私有数据写进仓库的 `work/`；
- macOS 私有目录使用 `0700` 和 `077` umask；Windows 默认写入当前账户的
  LocalAppData 并继承该账户的 NTFS 权限；
- profile 名会先验证再哈希，不能用 `../` 或绝对路径逃逸；
- 旧输出和旧 `runtime/work/` 会原样保留，新版不会自动跨命名空间读取。

同一个登录账户需要分开本地工作区时，可以增加 `--profile <本地英文代号>`。这只隔离
工具文件；同一个系统账户仍共享微信登录和桌面会话。不同人需要真实安全隔离时，应使用
不同的 macOS/Windows 账户。

## 第一次安装会做什么

Codex 先运行只读检查：

```text
python scripts/bootstrap.py doctor
```

用户要求安装或使用后，才会运行：

```text
python scripts/bootstrap.py install
```

安装器只做三件事：

1. 把运行源码复制到当前用户的私有应用目录；
2. 在私有 venv 中安装固定版本、固定哈希、与当前系统匹配的
   `imageio-ffmpeg` wheel；
3. 安装 `weixin-replay-to-mp3` Codex Skill。

它不使用 root/管理员权限，不退出微信，不读取聊天，不安装证书，不修改代理，也不会
因为“打开了 GitHub 仓库”就静默执行。

## 为什么这通常不是录一个小时

正常路径不是实时录音。macOS 自动入口和 Windows 手动播放接力之后都复用同一流程：

1. 把本次播放与精确短链接绑定；
2. 只冻结播放前后变化的安全运行文件；
3. 从同一上下文配对媒体地址和解密参数；
4. 先解密一小段并要求得到标准 MP4 头；
5. 按服务器声明的完整字节数并发、断点续传下载；
6. 转成 MP3，再用 ffmpeg 从头到尾完整解码。

因此主要耗时通常是源文件下载和转码，不受视频时长一比一限制。网络/CDN 限速仍会影响
速度，但已经下载且校验过的分片不会重下。系统音频录制只是明确的最后备选，不是正常
Windows 流程。

## 为什么不会发错群

macOS 自动发送前必须同时证明：

- 左侧名称是 `文件传输助手`；
- 右侧聊天标题是 `文件传输助手`；
- 左侧是文件传输助手的绿色图标；
- 最新消息状态能够验证；
- 点击后复制回来的完整链接与用户提供的链接一致。

任何一项不确定，都会在输入或发送前停止。白色/受保护截图不会被当成“微信退出”；
流程会改用外层微信进程、`WeChatAppEx`、辅助功能和 WindowServer 元数据，但不会解除
或破坏微信的窗口保护。

Windows 版本目前不自动发送，所以脚本不会误发到群聊。聊天选择和发送由用户完成；
Codex 必须说清楚“文件传输助手、最新同一链接、已经播放”三项并等待确认，不能把
“微信已打开”当成“目标已播放”。

## 手动命令（开发和排障）

macOS 安装目录：

```bash
python3 "$HOME/Library/Application Support/WeixinReplayToMP3/runtime/weixin_replay_cli.py" preflight
python3 "$HOME/Library/Application Support/WeixinReplayToMP3/runtime/weixin_replay_cli.py" \
  run "https://weixin.qq.com/sph/<id>"
```

Windows PowerShell 安装目录：

```powershell
python "$env:LOCALAPPDATA\WeixinReplayToMP3\runtime\weixin_replay_cli.py" preflight
python "$env:LOCALAPPDATA\WeixinReplayToMP3\runtime\weixin_replay_cli.py" `
  run "https://weixin.qq.com/sph/<id>"
```

Windows 命令明确要求手动播放时，先完成上文步骤并回复确认，再运行：

```powershell
python "$env:LOCALAPPDATA\WeixinReplayToMP3\runtime\weixin_replay_cli.py" `
  run "https://weixin.qq.com/sph/<id>" --manual-playback
```

如果用户已经有权保存并拿到本地 MP4/M4A 等文件，两端都可以跳过微信入口直接转换：

```text
python <运行目录>/weixin_replay_cli.py convert-file "<本地媒体文件>"
```

完整解码验证：

```text
python <运行目录>/weixin_replay_cli.py verify "<MP3 文件>"
```

如果用户明确知道最低时长，可增加 `--min-duration <秒>`。默认不假设视频一定是 60
分钟；完整性主要由精确链接、新增量、同上下文参数、MP4 头、完整字节数、候选大小和
最终完整解码共同证明。

## 隐私和安全

- 只处理用户本次提供的链接；
- 不读取微信聊天/联系人数据库；
- 不自动读取浏览器 Cookie、Keychain/Credential Manager 或账号 token；
- 不安装抓包证书，不修改系统代理，不运行第三方不透明下载器；
- 原始签名地址和解密参数只保存在当前用户/profile 的本机私有工作目录，不进入 Git
  或普通报告，也不会被另一个隔离命名空间自动读取；
- `work/`、输出媒体、截图、缓存和任务状态全部被发布检查排除。

详细边界见 [PRIVACY.md](PRIVACY.md)、[SECURITY.md](SECURITY.md) 和
[能力矩阵](docs/CAPABILITY_MAP.md)。

## 回归和发布检查

```text
python scripts/release_check.py
```

检查包括：代码/私密数据允许清单、绝对开发路径、凭据模式、大文件/媒体、Codex Skill、
安装器和不触碰真实微信的离线回归。GitHub Actions 会在 macOS 与 Windows 上分别安装
固定哈希的 FFmpeg wheel 并运行同一套测试；这不等同于 Windows 微信真机验证，真机
边界会继续明确标注。

## 许可证与声明

本仓库代码采用 MIT License。外部组件和算法说明见
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。项目与腾讯、微信、OpenAI 均无官方
隶属关系；用户必须只处理自己有权访问和转换的内容，并遵守当地法律及平台条款。
