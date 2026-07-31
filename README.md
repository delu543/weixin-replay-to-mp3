# 视频号链接转 MP3（Codex 工具）

把一个本人有权访问的视频号链接交给 Codex，自动通过 Mac 微信的
`文件传输助手`打开目标、抓取这次播放产生的新增量、下载并验证完整媒体，最后导出 MP3。

它的使用界面就是一个 Codex 对话窗口，不需要另外学习命令行。

## 最简单的使用方式

第一次，在 Codex 中发送这一句话：

```text
请读取 https://github.com/delu543/weixin-replay-to-mp3，按仓库说明安装并检查。
以后我在本窗口发送视频号链接时，直接帮我导出成 MP3。
```

安装检查通过后，日常只需要发送：

```text
https://weixin.qq.com/sph/<视频短链接 ID>
```

Codex 会返回最终文件路径、大小和时长。默认文件保存在：

```text
~/Downloads/WeixinReplayMP3/weixin_<短链接 ID>.mp3
```

同一链接再次发送时会先完整解码验证现有 MP3；验证通过就直接复用，不会再次操作
微信、重复下载或二次转码。中途断开时，目标绑定的抓取和分片下载状态也会继续使用。

## 当前支持范围

“任何人可使用”目前指任何满足以下条件的 Mac 用户，而不是 Windows/Linux 全平台：

- macOS；
- 官方 Mac 微信已登录；
- Python 3.9 或更高版本；
- Apple Swift Command Line Tools；
- Codex/Terminal 获得必要的辅助功能权限；
- 有足够空间保存原视频工作文件和最终 MP3。

Windows、Linux、Codex 云端环境不能控制本机 Mac 微信。仓库会明确报告
`unsupported_platform`，不会假装成功。

## 第一次安装会做什么

Codex 先运行只读检查：

```bash
python3 scripts/bootstrap.py doctor
```

用户要求安装或使用后，才会运行：

```bash
python3 scripts/bootstrap.py install
```

安装器只做三件事：

1. 把运行源码复制到当前用户的私有应用支持目录；
2. 在私有 venv 中安装固定版本、固定哈希的 `imageio-ffmpeg` macOS wheel；
3. 安装 `weixin-replay-to-mp3` Codex Skill。

它不使用 root，不退出微信，不读取聊天，不安装证书，不修改代理，也不会因为“打开了
GitHub 仓库”就静默执行。

## 为什么这不是录一个小时

正常路径不是实时录音：

1. 精确验证 `文件传输助手`，发送或复用本次链接；
2. 证明打开的是最新的同一链接，并证明视频真正播放；
3. 只冻结播放前后发生变化的安全运行文件；
4. 从同一上下文配对媒体地址和解密参数；
5. 先解密一小段，必须得到标准 MP4 头；
6. 按服务器声明的完整字节数并发、断点续传下载；
7. 转成 MP3，再用 ffmpeg 从头到尾完整解码。

因此主要耗时通常是源文件下载和转码，不受视频播放时长一比一限制。网络/CDN 限速仍会
影响速度，但已经下载且校验过的分片不会重下。

## 为什么不会发错群

发送前必须同时满足：

- 左侧名称是 `文件传输助手`；
- 右侧聊天标题是 `文件传输助手`；
- 左侧是文件传输助手的绿色图标；
- 最新消息状态能够验证；
- 点击后复制回来的完整链接与用户提供的链接一致。

任何一项不确定，流程都会在输入或发送前停止。白色/受保护截图不会被当成“微信退出”；
流程改用外层微信进程、`WeChatAppEx`、辅助功能和 WindowServer 元数据，但不会解除或
破坏微信的窗口保护。

## 手动命令（开发和排障）

安装后的只读检查：

```bash
python3 "$HOME/Library/Application Support/WeixinReplayToMP3/runtime/weixin_replay_cli.py" preflight
```

转换一个链接：

```bash
python3 "$HOME/Library/Application Support/WeixinReplayToMP3/runtime/weixin_replay_cli.py" \
  run "https://weixin.qq.com/sph/<id>"
```

完整解码验证一个 MP3：

```bash
python3 "$HOME/Library/Application Support/WeixinReplayToMP3/runtime/weixin_replay_cli.py" \
  verify "/path/to/file.mp3"
```

如果用户明确知道最低时长，可增加 `--min-duration <秒>`。默认不假设视频一定是 60 分钟；
完整性主要由精确链接、新增量、同上下文参数、MP4 头、完整字节数、候选大小和最终完整
解码共同证明。

## 隐私和安全

- 只处理用户本次提供的链接；
- 不读取微信聊天/联系人数据库；
- 不自动读取浏览器 Cookie、Keychain 或账号 token；
- 不安装抓包证书，不修改系统代理，不运行第三方不透明下载器；
- 原始签名地址和解密参数只保存在本机私有工作目录，不进入 Git 或普通报告；
- `work/`、输出媒体、截图、缓存和任务状态全部被发布检查排除。

详细边界见 [PRIVACY.md](PRIVACY.md)、[SECURITY.md](SECURITY.md) 和
[能力矩阵](docs/CAPABILITY_MAP.md)。

## 回归和发布检查

```bash
python3 scripts/release_check.py
```

检查包括：代码/私密数据允许清单、绝对开发路径、凭据模式、大文件/媒体、Codex Skill、
安装器静态检查，以及不触碰真实微信的离线回归测试。

## 许可证与声明

本仓库代码采用 MIT License。外部组件和算法说明见
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。项目与腾讯、微信、OpenAI 均无官方
隶属关系；用户必须只处理自己有权访问和转换的内容，并遵守当地法律及平台条款。
