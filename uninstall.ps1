param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ArgsRemaining
)

# RootSeeker 卸载：停止 Docker/本机进程，并清理全部安装产物
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = $null
# Prefer system Python so this process does not lock .venv (we delete it).
foreach ($candidate in @(
        "python",
        "python3",
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "C:\Users\Administrator\AppData\Local\Python\pythoncore-3.14-64\python.exe",
        "C:\Users\Administrator\AppData\Local\Python\pythoncore-3.11-64\python.exe",
        (Join-Path $PSScriptRoot ".venv\Scripts\python.exe")
    )) {
    try {
        $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($cmd) {
            $python = $cmd.Source
            break
        }
        if (Test-Path $candidate) {
            $python = $candidate
            break
        }
    } catch {
    }
}

if (-not $python) {
    Write-Host "[错误] 未找到 Python，请先安装 Python 3.11+"
    exit 1
}

Write-Host "[信息] 开始卸载（将删除 .env / .venv / .tools / data / Docker volumes 等）"
& $python "$PSScriptRoot\scripts\uninstall.py" @ArgsRemaining
exit $LASTEXITCODE
