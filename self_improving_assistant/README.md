# Self-Improving Assistant

Ce projet lance une appli web (FastAPI) avec un tableau de bord pour évaluer, faire de l'A/B test, promouvoir un prompt, apprendre du web (RAG) et optionnellement s'auto‑mettre à jour.

Ci‑dessous, toutes les commandes PowerShell pour Windows en supposant une installation sur `D:\ia\self_improving_assistant`.

## Prérequis (Windows)

* Windows 10/11
* Python 3.9+ installé et disponible dans PowerShell (`py -3 -V` ou `python -V`)
* Accès Internet si vous utilisez OpenAI ou l’apprentissage web

## Installation (Windows / PowerShell)

### Option A — Installation 1‑clic (recommandé)

1. Copiez le dossier `self_improving_assistant` sur votre PC Windows (ex: `D:\ia\self_improving_assistant`).
2. Double‑cliquez `install_windows.bat`.
   - Le script élève les droits administrateur puis lance `scripts/install_and_setup.ps1`.
   - Ce script:
     - installe Python 3.11 si nécessaire (via winget ou installeur officiel silencieux),
     - crée le venv et installe les dépendances (requirements.txt),
     - ouvre le port 8000 dans le pare‑feu Windows,
     - crée/actualise les tâches planifiées (`SIA_Server` au logon + jobs nocturnes),
     - crée 2 raccourcis sur le Bureau: « SIA - Démarrer le serveur » et « SIA - Dashboard ».

Après l'installation:
- Le serveur démarre automatiquement à votre connexion (tâche planifiée `SIA_Server`).
- Le dashboard est accessible sur http://127.0.0.1:8000
- Vous pouvez lancer manuellement via les raccourcis Bureau.

### Option B — Manuel (déjà existant)

```powershell
New-Item -ItemType Directory -Path 'D:\ia\self_improving_assistant' -Force | Out-Null
Set-Location 'D:\ia\self_improving_assistant'

# Copier/extraire le projet OU cloner
# git clone <URL_DU_DEPOT> .

# Créer/activer le venv puis installer les dépendances
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# (Optionnel) Clé OpenAI pour résumer les pages lors de l'ingestion
setx OPENAI_API_KEY "sk-..."   # persistant pour l’utilisateur
```

## Démarrer le serveur web (Windows)

```powershell
# Depuis D:\ia\self_improving_assistant (venv activé)
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
# Ouvrir ensuite http://localhost:8000 dans le navigateur
```

## Scripts Windows fournis

```powershell
# Depuis D:\ia\self_improving_assistant
.\run_server.bat      # lance le serveur FastAPI (dashboard)
.\run_eval.bat        # évaluation
.\run_abtest.bat      # A/B test
.\run_promote.bat     # promotion
```

## Lancer les scripts manuellement

```powershell
# Évaluer (génère logs\eval_*.csv)
python scripts\evaluate.py

# A/B test (génère logs\abtest_*.csv et logs\last_winner.txt)
python scripts\ab_test.py

# Promouvoir le meilleur candidat si gain suffisant
python scripts\promote.py

# Générer de nouveaux candidats de prompt
python scripts\grow.py

# (Optionnel) Auto‑mise à jour du code si activée dans la config
python scripts\self_update.py
```

## Automatisation (Windows Task Scheduler)

```powershell
# Si PowerShell bloque les scripts, autoriser localement
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned -Force

# Créer les tâches planifiées (server au logon + éval + A/B + promotion)
.\setup_tasks.ps1

Après cela:
- SIA_Server démarre automatiquement le serveur à l’ouverture de session et le garde actif.
- SIA_Evaluate / SIA_ABTest / SIA_Promote tournent la nuit (horaires dans setup_tasks.ps1).
```

### Option C — Générer un EXE d’installation

Si vous souhaitez un exécutable autonome « SIA‑Installer.exe » pour distribuer l’installation:

1. Sur une machine Windows, installez PyInstaller: `py -3 -m pip install pyinstaller`
2. Depuis le dossier `self_improving_assistant`, exécutez: `py -3 scripts/build_windows_installer.py`
3. Récupérez `dist/SIA-Installer.exe`.

Au lancement, cet EXE appellera le script PowerShell d'installation (`scripts/install_and_setup.ps1`).

## Configuration du provider LLM (facultatif)

* Fichier: `configs/config.yaml`
* Par défaut `provider: "dummy"` (réponses de test). Pour OpenAI:

```yaml
provider: "openai"
model: "gpt-4o-mini"
```

* Clé OpenAI en variable d’environnement:

```powershell
$env:OPENAI_API_KEY = 'sk-...'           # pour la session courante
# ou de façon persistante (utilisateur)
[Environment]::SetEnvironmentVariable('OPENAI_API_KEY','sk-...','User')
```

* Pour un modèle local (Ollama), lancez Ollama, puis mettez `provider: "ollama"` et `model: "llama3"` (ou autre modèle installé).

## Mode rafale (burst) et parallélisme

* Dans `configs/config.yaml`:

```yaml
scheduler:
  enabled: true
  burst: true           # enchaîne les cycles avec un petit délai (interval_seconds)
  interval_seconds: 5

evaluation:
  parallel_workers: auto  # utilise (CPU-1) threads, ou fixer un entier
```

## Dépannage courant

* “Execution of scripts is disabled on this system” lors de l’activation du venv:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned -Force
.\.venv\Scripts\Activate.ps1
```

* “python n’est pas reconnu” : réinstallez Python depuis python.org et cochez “Add to PATH”.
* Erreur “python n’est pas reconnu”: réinstallez Python depuis python.org et cochez “Add to PATH”.
* Port 8000 occupé: changez `--port 8001`.

## (Optionnel) macOS — démarrage et automatisation

Voir les scripts `scripts/run_server.sh` et `scripts/install_launchd.sh`.

## Structure utile

* `app/main.py` — serveur FastAPI + dashboard/web API
* `configs/config.yaml` — configuration générale
* `scripts/` — évaluation, A/B, promotion, croissance, auto‑update
* `prompts/` — prompts actif et candidats
* `data/tests.jsonl` — tests
* `logs/` — résultats générés (CSV, etc.)

Bon démarrage !
