param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ArgsRemaining
)

# RootSeeker 国内安装入口：Docker / 下载走国内加速源
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$env:ROOTSEEKER_SETUP_REGION = "cn"
Write-Host "[信息] 使用国内加速安装脚本 (setup-cn.ps1)"

& "$PSScriptRoot\setup.ps1" @ArgsRemaining
exit $LASTEXITCODE
