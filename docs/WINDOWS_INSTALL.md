# Windows 安装与救援（v0.4.1）

这个版本把“取得安装器”和“取得源码”合并成一个步骤。`install-windows.ps1`
内置固定版本的最小源码包，并在解压前校验源码包的长度、SHA-256、路径、版本和必需
文件。因此 Windows 不需要 Git、Git HTTPS helper、GitHub ZIP 或
`raw.githubusercontent.com`。

## Codex 直接执行

在 Windows 原生 PowerShell 中运行。命令会依次尝试三个 jsDelivr 入口，并在执行前校验
整个安装器文件的固定 SHA-256：

```powershell
$installer = Join-Path $env:TEMP "weixin-replay-to-mp3-v0.4.1.ps1"
$expected = "b48ef5caa9efbd675cc63d5724d966223abf3f6bb958efab642826f6d08c943c"
$urls = @(
  "https://cdn.jsdelivr.net/gh/delu543/weixin-replay-to-mp3@v0.4.1/install-windows.ps1",
  "https://fastly.jsdelivr.net/gh/delu543/weixin-replay-to-mp3@v0.4.1/install-windows.ps1",
  "https://gcore.jsdelivr.net/gh/delu543/weixin-replay-to-mp3@v0.4.1/install-windows.ps1"
)
$downloaded = $false
foreach ($url in $urls) {
  try {
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $installer
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $installer).Hash.ToLowerInvariant()
    if ($actual -ne $expected) { throw "installer SHA-256 mismatch" }
    $downloaded = $true
    break
  } catch { }
}
if (-not $downloaded) { throw "All verified installer download channels failed" }
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $installer
```

安装器会自动发现 Python 3.10+；缺少时通过 `winget` 安装当前用户范围的 Python 3.12。
随后在 `%LOCALAPPDATA%\WeixinReplayToMP3\` 下展开已校验源码，并把固定哈希的 FFmpeg、
yt-dlp、EJS 和 Deno 安装到私有 venv。Git 和系统 FFmpeg 都不是必需项。

成功必须同时满足：安装命令退出码为 0、最终 JSON 为 `status: ready`、doctor 通过，并
出现 `READY: you can send a link now`。只看到下载开始或依赖列表不算成功。

## 所有下载入口都被拦截

在另一台可联网设备下载同一个 `v0.4.1/install-windows.ps1`，核对上面的 SHA-256 后，
通过 U 盘、局域网或用户选择的文件传输方式复制到 Windows 电脑。然后直接运行：

```powershell
$actual = (Get-FileHash -Algorithm SHA256 -LiteralPath .\install-windows.ps1).Hash.ToLowerInvariant()
if ($actual -ne "b48ef5caa9efbd675cc63d5724d966223abf3f6bb958efab642826f6d08c943c") {
  throw "installer SHA-256 mismatch"
}
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install-windows.ps1
```

不需要另行打包或传输仓库 ZIP。这个单文件已经包含可审计源码救援包。首次安装 Python
和私有依赖仍需访问 Microsoft/Python 包源；如果这些网络也不可达，就属于依赖源网络
问题，而不是 GitHub/仓库问题，不能伪报工具已就绪。

## 只读检查

不安装依赖、只验证 Windows 环境和内置源码时：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install-windows.ps1 -CheckOnly
```

正确结果应包含 `source_strategy: embedded_verified_bundle`、
`embedded_source_ready: true`、`github_source_required: false` 和版本 `0.4.1`。本工具必须
在 Codex 的 Windows native 环境中运行；WSL/Linux 的 `unsupported_platform` 不能当成
Windows 结果。
