param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ArgsRemaining
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = $null
$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
foreach ($candidate in @(
        $venvPython,
        "python",
        "python3",
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "C:\Users\Administrator\AppData\Local\Python\pythoncore-3.14-64\python.exe"
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

& $python "$PSScriptRoot\scripts\setup_wizard.py" @ArgsRemaining
exit $LASTEXITCODE
