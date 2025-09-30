# Self-Improving Assistant

Ce projet lance une appli web (FastAPI) avec un tableau de bord pour évaluer, faire de l'A/B test, promouvoir un prompt, apprendre du web (RAG) et optionnellement s'auto‑mettre à jour.

Ci‑dessous, toutes les commandes PowerShell pour Windows en supposant une installation sur `D:\ia\self_improving_assistant`.

## Prérequis

* Windows 10/11
* Python 3.9+ installé et disponible dans PowerShell (`python -V`)
* Accès Internet si vous utilisez OpenAI ou l’apprentissage web

## Installation (PowerShell)

```powershell
# 1) Créer le dossier de travail sur D:\
New-Item -ItemType Directory -Path 'D:\ia\self_improving_assistant' -Force | Out-Null
Set-Location 'D:\ia\self_improving_assistant'

# 2) Copier/extraire le projet ici OU cloner un dépôt git
# git clone <URL_DU_DEPOT> .

# 3) Créer et activer l'environnement virtuel
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 4) Mettre à jour pip et installer les dépendances
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Démarrer le serveur web

```powershell
# Depuis D:\ia\self_improving_assistant (venv activé)
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
# Ouvrir ensuite http://localhost:8000 dans le navigateur
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

## Utiliser les .bat fournis (option Windows)

```powershell
# Depuis D:\ia\self_improving_assistant
.\run_eval.bat
.\run_abtest.bat
.\run_promote.bat
```

Ces scripts créent le venv si nécessaire, installent les dépendances puis lancent l’action.

## Tâches planifiées (Windows Task Scheduler)

```powershell
# Si PowerShell bloque les scripts, autoriser localement
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned -Force

# Créer les tâches planifiées (éval, A/B, promotion)
.\setup_tasks.ps1
```

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
* Avertissement urllib3/LibreSSL (non bloquant) vu sur macOS — pas concerné sur Windows.

## Structure utile

* `app/main.py` — serveur FastAPI + dashboard/web API
* `configs/config.yaml` — configuration générale
* `scripts/` — évaluation, A/B, promotion, croissance, auto‑update
* `prompts/` — prompts actif et candidats
* `data/tests.jsonl` — tests
* `logs/` — résultats générés (CSV, etc.)

Bon démarrage !
