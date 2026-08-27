# Windows 安装与救援（v0.4.2）

这个版本把“取得安装器”和“取得源码”合并成一个步骤。`install-windows.ps1`
内置固定版本的最小源码包，并在解压前校验源码包的长度、SHA-256、路径、版本和必需
文件。因此 Windows 不需要 Git、Git HTTPS helper、GitHub ZIP 或
`raw.githubusercontent.com`。

## 固定发布校验值

| 文件 | 字节数 | SHA-256 |
| --- | ---: | --- |
| `bootstrap-windows.ps1` | 13,579 | `b00496f07c6e1812486d741fc32fd4a15d406048aec1375bfa7bb2157d4c3a86` |
| `install-windows.ps1` | 1,532,424 | `44c28379bf01a22cbcc1548f33de3e194cad11841539d803f061bf481604758a` |

任何来源只要字节数或 SHA-256 不一致就不执行。

## 有本地仓库时

在 Windows 原生 PowerShell 中运行。如果 Codex 的工作区依赖工具返回了 bundled Python，
把其精确路径直接传入；没有就省略该参数：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\bootstrap-windows.ps1 `
  -PythonExecutable "<CODEX 返回的精确 Windows Python 路径>"
```

## 没有本地仓库：先取得小型 bootstrap

PowerShell 能访问 `api.github.com` 时：

```powershell
$bootstrap = Join-Path $env:TEMP "bootstrap-windows-v0.4.2.ps1"
$headers = @{
  Accept = "application/vnd.github.raw+json"
  "X-GitHub-Api-Version" = "2022-11-28"
  "User-Agent" = "weixin-replay-to-mp3-bootstrap/0.4.2"
}
$url = "https://api.github.com/repos/delu543/weixin-replay-to-mp3/contents/bootstrap-windows.ps1?ref=v0.4.2"
Invoke-WebRequest -UseBasicParsing -Uri $url -Headers $headers -OutFile $bootstrap -TimeoutSec 30
if ((Get-Item -LiteralPath $bootstrap).Length -ne 13579) { throw "bootstrap length mismatch" }
$actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $bootstrap).Hash.ToLowerInvariant()
if ($actual -ne "b00496f07c6e1812486d741fc32fd4a15d406048aec1375bfa7bb2157d4c3a86") {
  throw "bootstrap SHA-256 mismatch"
}
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $bootstrap
```

如果 PowerShell 网络失败但 Codex 提供 bundled Python，用该 Python 执行同一个 API 请求：

```powershell
$python = "<CODEX 返回的精确 Windows Python 路径>"
$bootstrap = Join-Path $env:TEMP "bootstrap-windows-v0.4.2.ps1"
$url = "https://api.github.com/repos/delu543/weixin-replay-to-mp3/contents/bootstrap-windows.ps1?ref=v0.4.2"
$code = 'import hashlib,sys,urllib.request; u,o=sys.argv[1:3]; r=urllib.request.Request(u,headers={"Accept":"application/vnd.github.raw+json","User-Agent":"weixin-replay-to-mp3-bootstrap/0.4.2"}); d=urllib.request.urlopen(r,timeout=45).read(); assert len(d)==13579 and hashlib.sha256(d).hexdigest()=="b00496f07c6e1812486d741fc32fd4a15d406048aec1375bfa7bb2157d4c3a86"; open(o,"wb").write(d)'
& $python -c $code $url $bootstrap
if ($LASTEXITCODE -ne 0) { throw "bundled Python could not acquire the verified bootstrap" }
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $bootstrap -PythonExecutable $python
```

## 浏览器能看 GitHub、终端不能下载

这是自动恢复分支，不应立即让用户手工搬文件。Codex 用内置浏览器打开：

```text
https://github.com/delu543/weixin-replay-to-mp3/blob/v0.4.2/bootstrap-windows.ps1
```

读取完整的 13,579 字节 ASCII 源码，精确写入本地 `bootstrap-windows.ps1`；按上表验证后
运行。若浏览器能保存以下任一文件，也可直接作为本地输入：

```text
https://github.com/delu543/weixin-replay-to-mp3/releases/download/v0.4.2/install-windows.ps1
https://codeload.github.com/delu543/weixin-replay-to-mp3/zip/refs/tags/v0.4.2
```

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\bootstrap-windows.ps1 `
  -LocalArtifact "<浏览器实际保存的 ps1 或 zip 路径>" `
  -PythonExecutable "<可选的 bundled Python 路径>"
```

bootstrap 自动尝试 GitHub Contents API、base64 Git blob、Release Asset、codeload 和三个
jsDelivr 节点；每个节点可用 PowerShell、`curl.exe` 或显式 Python。失败 JSON 会列出
transport/client，不再用一个笼统的“网络失败”结论，也不会无限等待。

安装器会自动发现 Python 3.10+；缺少时通过 `winget` 安装当前用户范围的 Python 3.12。
随后在 `%LOCALAPPDATA%\WeixinReplayToMP3\` 下展开已校验源码，并把固定哈希的 FFmpeg、
yt-dlp、EJS 和 Deno 安装到私有 venv。Git 和系统 FFmpeg 都不是必需项。

成功必须同时满足：安装命令退出码为 0、最终 JSON 为 `status: ready`、doctor 通过，并
出现 `READY: you can send a link now`。只看到下载开始或依赖列表不算成功。

## 所有自动入口确实被拦截

在另一台可联网设备下载同一个 `v0.4.2/install-windows.ps1`，核对上面的 SHA-256 后，
通过 U 盘、局域网或用户选择的文件传输方式复制到 Windows 电脑。然后直接运行：

```powershell
$actual = (Get-FileHash -Algorithm SHA256 -LiteralPath .\install-windows.ps1).Hash.ToLowerInvariant()
if ($actual -ne "44c28379bf01a22cbcc1548f33de3e194cad11841539d803f061bf481604758a") {
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
`embedded_source_ready: true`、`github_source_required: false` 和版本 `0.4.2`。本工具必须
在 Codex 的 Windows native 环境中运行；WSL/Linux 的 `unsupported_platform` 不能当成
Windows 结果。
