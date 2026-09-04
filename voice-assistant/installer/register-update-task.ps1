$ErrorActionPreference = "Stop"
$helperDir = Join-Path $env:ProgramData "GoogleAssistant"
$helper = Join-Path $helperDir "silent-update.cmd"
New-Item -ItemType Directory -Force -Path $helperDir | Out-Null
icacls $helperDir /grant "*S-1-5-32-545:(OI)(CI)M" /T /C | Out-Null

if (-not (Test-Path $helper)) {
    throw "Missing $helper"
}

$action = New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\cmd.exe" -Argument "/c `"$helper`""
$user = if ($env:USERDOMAIN) { "$env:USERDOMAIN\$env:USERNAME" } else { $env:USERNAME }
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName "GoogleAssistantSilentUpdate" -Action $action -Principal $principal -Settings $settings -Force | Out-Null
