# setup_tasks.ps1 — version corrigée et robuste
# Exécuter depuis D:\ia\self_improving_assistant

$ErrorActionPreference = "Stop"

# Répertoire racine = dossier du script
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

# Chemins des .bat
$evalBat    = Join-Path $root "run_eval.bat"
$abtestBat  = Join-Path $root "run_abtest.bat"
$promoteBat = Join-Path $root "run_promote.bat"

# Vérif présence .bat (on NE copie pas s'ils existent déjà)
foreach ($f in @($evalBat, $abtestBat, $promoteBat)) {
    if (-not (Test-Path $f)) {
        throw "Fichier manquant: $f. Place les .bat dans $root avant de lancer ce script."
    }
}

# Nettoyage (évite les échecs si la tâche existe déjà)
$taskNames = @("SIA_Evaluate","SIA_ABTest","SIA_Promote")
foreach ($t in $taskNames) {
    try { Unregister-ScheduledTask -TaskName $t -Confirm:$false -ErrorAction SilentlyContinue } catch {}
}

# Définition du principal (utilisateur courant, session interactive)
$user = "$env:UserDomain\$env:UserName"
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Highest

# Triggers quotidiens (à adapter si tu veux)
$trigger1 = New-ScheduledTaskTrigger -Daily -At 03:00
$trigger2 = New-ScheduledTaskTrigger -Daily -At 03:15
$trigger3 = New-ScheduledTaskTrigger -Daily -At 03:25

# Actions — pour .bat, on passe par cmd.exe /c "..." (meilleure compatibilité et quoting)
$action1 = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$evalBat`""
$action2 = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$abtestBat`""
$action3 = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$promoteBat`""

# Réglages de la tâche (robustes sur portables et retards éventuels)
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

# Enregistrement des tâches
Register-ScheduledTask -TaskName "SIA_Evaluate" -Action $action1 -Trigger $trigger1 -Principal $principal -Settings $settings | Out-Null
Register-ScheduledTask -TaskName "SIA_ABTest"   -Action $action2 -Trigger $trigger2 -Principal $principal -Settings $settings | Out-Null
Register-ScheduledTask -TaskName "SIA_Promote"  -Action $action3 -Trigger $trigger3 -Principal $principal -Settings $settings | Out-Null

Write-Host "Tasks created:"
Write-Host " - SIA_Evaluate @ 03:00"
Write-Host " - SIA_ABTest   @ 03:15"
Write-Host " - SIA_Promote  @ 03:25"
