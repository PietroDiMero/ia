## Creates three Scheduled Tasks to automate your self-improving assistant
## Run this from an elevated PowerShell (Run as Administrator)

$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$evalBat     = Join-Path $projectDir "run_eval.bat"
$abtestBat   = Join-Path $projectDir "run_abtest.bat"
$promoteBat  = Join-Path $projectDir "run_promote.bat"

# If the BAT files are not in the project directory yet, copy them from the current dir
if (Test-Path ".\run_eval.bat") { Copy-Item ".\run_eval.bat" $evalBat -Force }
if (Test-Path ".\run_abtest.bat") { Copy-Item ".\run_abtest.bat" $abtestBat -Force }
if (Test-Path ".\run_promote.bat") { Copy-Item ".\run_promote.bat" $promoteBat -Force }

$principal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -LogonType InteractiveToken
$settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

$action1 = New-ScheduledTaskAction -Execute $evalBat
$trigger1 = New-ScheduledTaskTrigger -Daily -At 3:00AM
Register-ScheduledTask -TaskName "SIA_Evaluate" -Action $action1 -Trigger $trigger1 -Principal $principal -Settings $settings -Force

$action2 = New-ScheduledTaskAction -Execute $abtestBat
$trigger2 = New-ScheduledTaskTrigger -Daily -At 3:15AM
Register-ScheduledTask -TaskName "SIA_ABTest" -Action $action2 -Trigger $trigger2 -Principal $principal -Settings $settings -Force

$action3 = New-ScheduledTaskAction -Execute $promoteBat
$trigger3 = New-ScheduledTaskTrigger -Daily -At 3:25AM
Register-ScheduledTask -TaskName "SIA_Promote" -Action $action3 -Trigger $trigger3 -Principal $principal -Settings $settings -Force

Write-Host @"
Tasks created:
 - SIA_Evaluate @ 03:00
 - SIA_ABTest   @ 03:15
 - SIA_Promote  @ 03:25
"@
