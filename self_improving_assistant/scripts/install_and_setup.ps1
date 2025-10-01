<#
  install_and_setup.ps1 — Installe et configure automatiquement Self‑Improving Assistant sur Windows.
  - Vérifie/installe Python 3.x (winget si dispo, sinon installeur officiel silencieux)
  - Crée l'environnement virtuel et installe les dépendances
  - Ouvre le port 8000 dans le pare-feu Windows (local)
  - Crée/actualise les tâches planifiées (server au logon + jobs nocturnes)
  - Crée des raccourcis sur le Bureau

  À exécuter en Administrateur (le script s'auto‑élève si nécessaire).
#>

$ErrorActionPreference = "Stop"
try { Stop-Transcript | Out-Null } catch {}
$logPath = Join-Path $env:TEMP "SIA_install_$(Get-Date -Format yyyyMMdd_HHmmss).log"
Start-Transcript -Path $logPath -Force | Out-Null

function Assert-Admin {
    $currentUser = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $currentUser.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Write-Host "Élévation des privilèges requise…" -ForegroundColor Yellow
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = 'powershell.exe'
        $psi.Arguments = "-ExecutionPolicy Bypass -File `"$PSCommandPath`""
        $psi.Verb = 'runas'
        try { [Diagnostics.Process]::Start($psi) | Out-Null } catch { throw "Élévation refusée." }
        exit 0
    }
}

function Test-Command($name){ try { Get-Command $name -ErrorAction Stop | Out-Null; return $true } catch { return $false } }

function Install-Python {
    if (Test-Command 'py') { return }
    Write-Host "Python non trouvé — tentative d'installation…" -ForegroundColor Yellow
    if (Test-Command 'winget') {
        try {
            winget install -e --id Python.Python.3.11 --source winget --accept-package-agreements --accept-source-agreements -h | Out-Null
        } catch { Write-Warning "winget a échoué: $_" }
        if (Test-Command 'py') { return }
    }
    # Fallback: installeur officiel silencieux (x64)
    $url = 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe'
    $tmp = Join-Path $env:TEMP 'python311_installer.exe'
    Write-Host "Téléchargement de Python depuis python.org…" -ForegroundColor Yellow
    Invoke-WebRequest -Uri $url -OutFile $tmp -UseBasicParsing
    Write-Host "Installation silencieuse de Python…" -ForegroundColor Yellow
    Start-Process -FilePath $tmp -ArgumentList '/quiet InstallAllUsers=1 PrependPath=1 Include_launcher=1 Include_test=0' -Wait
    Remove-Item $tmp -Force -ErrorAction SilentlyContinue
    if (-not (Test-Command 'py')) { throw "Installation de Python échouée. Installe Python manuellement puis relance ce script." }
}

function Ensure-Venv-And-Dependencies($root){
    Set-Location $root
    $venv = Join-Path $root '.venv'
    if (-not (Test-Path $venv)) {
        Write-Host "Création de l'environnement virtuel…"
        py -3 -m venv .venv
    }
    $python = Join-Path $venv 'Scripts/python.exe'
    if (-not (Test-Path $python)) { throw "Python venv introuvable: $python" }
    Write-Host "Installation des dépendances…"
    & $python -m pip install --disable-pip-version-check -r (Join-Path $root 'requirements.txt')
}

function Open-Firewall {
    try {
        if (-not (Get-NetFirewallRule -DisplayName 'SIA FastAPI 8000' -ErrorAction SilentlyContinue)){
            New-NetFirewallRule -DisplayName 'SIA FastAPI 8000' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000 -Profile Any | Out-Null
        }
    } catch { Write-Warning "Pare-feu: $_" }
}

function Register-Tasks($root){
    $setup = Join-Path $root 'setup_tasks.ps1'
    if (-not (Test-Path $setup)) { throw "setup_tasks.ps1 introuvable dans $root" }
    Write-Host "Création/actualisation des tâches planifiées…"
    powershell -ExecutionPolicy Bypass -File $setup | Write-Host
}

function Create-Shortcuts($root){
    $ws = New-Object -ComObject WScript.Shell
    $desktop = [Environment]::GetFolderPath('Desktop')
    # Raccourci serveur
    $lnk1 = Join-Path $desktop 'SIA - Démarrer le serveur.lnk'
    $target1 = Join-Path $root 'run_server.bat'
    $sc1 = $ws.CreateShortcut($lnk1)
    $sc1.TargetPath = 'cmd.exe'
    $sc1.Arguments = "/c `"$target1`""
    $sc1.WorkingDirectory = $root
    $sc1.IconLocation = 'shell32.dll, 220'
    $sc1.Save()
    # Raccourci Dashboard
    $lnk2 = Join-Path $desktop 'SIA - Dashboard.lnk'
    $sc2 = $ws.CreateShortcut($lnk2)
    $sc2.TargetPath = 'powershell.exe'
    $sc2.Arguments = '-NoLogo -NoProfile -WindowStyle Hidden -Command start http://127.0.0.1:8000'
    $sc2.IconLocation = 'shell32.dll, 220'
    $sc2.Save()
}

try {
    Assert-Admin
    $root = Split-Path -Parent $MyInvocation.MyCommand.Path
    # Répertoire projet = dossier parent du script (self_improving_assistant)
    Set-Location $root
    Write-Host "Dossier d'installation: $root" -ForegroundColor Cyan

    Install-Python
    Ensure-Venv-And-Dependencies -root $root
    Open-Firewall
    Register-Tasks -root $root
    Create-Shortcuts -root $root

    Write-Host "Installation terminée." -ForegroundColor Green
    Write-Host "- Le serveur démarrera automatiquement à la connexion (tâche SIA_Server)."
    Write-Host "- Lancement manuel: double-clique le raccourci 'SIA - Démarrer le serveur' sur le Bureau."
    Write-Host "- Ouvre le Dashboard: 'SIA - Dashboard' ou http://127.0.0.1:8000"
    Write-Host "Journal: $logPath"
}
catch {
    Write-Error $_
    Write-Host "Journal: $logPath" -ForegroundColor Yellow
    exit 1
}
finally { try { Stop-Transcript | Out-Null } catch {} }
