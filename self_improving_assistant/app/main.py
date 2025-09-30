from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel
import os, yaml, glob, subprocess, sys, asyncio
from datetime import datetime
from pathlib import Path
from app.tools.web_rag import TinyRAG, learn_from_web

app = FastAPI()

# -----------------------------------------------------------------------------
# Config helpers
# -----------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

def _abs(p: str) -> str:
    # Convertit un chemin relatif (depuis la racine du projet) en absolu
    return str((BASE_DIR / p).resolve())

def load_config():
    with open(_abs("configs/config.yaml"), "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def load_prompt(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""

# -----------------------------------------------------------------------------
# Dummy LLM (remplace plus tard par un appel réel OpenAI/Ollama, etc.)
# -----------------------------------------------------------------------------
def call_llm(prompt, question, provider="dummy", model=""):
    provider = (provider or "dummy").lower()
    # Real providers
    if provider == "openai":
        try:
            from openai import OpenAI
            client = OpenAI()
            resp = client.chat.completions.create(
                model=model or "gpt-4o-mini",
                messages=[
                    {"role": "system", "content": prompt or ""},
                    {"role": "user", "content": question},
                ],
                temperature=0.2,
                max_tokens=500,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as e:
            return f"[openai error] {e}"
    if provider == "ollama":
        try:
            import requests
            payload = {
                "model": model or "llama3",
                "messages": [
                    {"role": "system", "content": prompt or ""},
                    {"role": "user", "content": question},
                ],
                "stream": False,
                "options": {"temperature": 0.2}
            }
            r = requests.post("http://localhost:11434/api/chat", json=payload, timeout=60)
            r.raise_for_status()
            data = r.json()
            return (data.get("message", {}).get("content") or data.get("response") or "").strip()
        except Exception as e:
            return f"[ollama error] {e}"
    # Dummy heuristic fallback
    q = question.lower()
    if "riz" in q:
        return "En général, compte 60 à 80 g de riz cru par personne."
    if "ls" in q or "macos" in q:
        return "Utilise `ls -la` dans le terminal pour lister les fichiers (y compris cachés)."
    if "ram" in q:
        return "La RAM est une mémoire vive temporaire; le stockage (disque) conserve les données de façon plus permanente."
    return "Voici une réponse générique (dummy)."

# -----------------------------------------------------------------------------
# API /ask
# -----------------------------------------------------------------------------
class AskReq(BaseModel):
    question: str
    use_rag: bool = False

@app.post("/ask")
def ask(req: AskReq):
    cfg = load_config()
    prompt = load_prompt(cfg["paths"]["active_prompt"])
    context = ""
    if req.use_rag:
        rag = TinyRAG(_abs("data/rag.jsonl"))
        docs = rag.query(req.question, top_k=3)
        if docs:
            joined = "\n---\n".join(d["text"][:1000] for d in docs)
            context = f"\n\n[Contexte]\n{joined}\n\n"
    sys_prompt = (prompt or "") + context
    answer = call_llm(sys_prompt, req.question, cfg.get("provider", "dummy"), cfg.get("model", ""))
    return {"answer": answer}

# -----------------------------------------------------------------------------
# Dashboard (HTML)
# -----------------------------------------------------------------------------
DASH_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Self-Improving Assistant – Dashboard</title>
  <style>
    :root { font-family: ui-sans-serif, system-ui, sans-serif; color-scheme: light dark; }
    body { margin: 0; padding: 16px; }
    header { display:flex; gap:12px; align-items:center; margin-bottom: 12px; flex-wrap: wrap; }
    button { padding:8px 12px; border-radius:10px; border:1px solid #8884; cursor:pointer; }
    .grid { display:grid; grid-template-columns: 1fr 1fr; gap:16px; }
    .card { border:1px solid #8884; border-radius:16px; padding:12px; background:rgba(127,127,127,0.05); }
    h1,h2,h3 { margin:0 0 8px; }
    pre { background:#0002; padding:8px; border-radius:8px; max-height:50vh; overflow:auto; white-space:pre-wrap; }
    table { width:100%; border-collapse: collapse; }
    th,td { border-bottom:1px solid #8883; padding:6px 8px; text-align:left; }
    small{opacity:.7}
    .row{display:flex; gap:10px; align-items:center; flex-wrap:wrap;}
    code{background:#0002; padding:2px 6px; border-radius:6px;}
  </style>
</head>
<body>
  <header>
    <h1 style="margin:0;">Self-Improving Assistant — Dashboard</h1>
    <div class="row">
      <button onclick="run('evaluate')">▶ Évaluer</button>
      <button onclick="run('ab_test')">▶ A/B test</button>
      <button onclick="run('promote')">▶ Promouvoir</button>
    <button onclick="learn()">🔎 Apprendre du web</button>
            <button onclick="run('grow')">🌱 Générer candidats</button>
    <button onclick="run('self_update')">🤖 Auto‑update code</button>
      <button onclick="sched('start')">⏵ Auto ON</button>
      <button onclick="sched('stop')">⏸ Auto OFF</button>
      <button onclick="status()">ℹ️ Statut</button>
      <small id="status"></small>
    </div>
  </header>

  <div class="grid">
    <section class="card">
      <h2>📜 Logs (cron.log)</h2>
      <div class="row">
        <button onclick="refreshLog()">⟳ Actualiser</button>
        <small>auto-refresh toutes les 2s</small>
      </div>
      <pre id="log">Chargement…</pre>
    </section>

    <section class="card">
      <h2>🧪 Derniers résultats</h2>
      <div id="files"></div>
      <h3>Prompt actif</h3>
      <pre id="prompt">Chargement…</pre>
            <h3>Poser une question</h3>
            <div>
                        <textarea id="q" rows="3" style="width:100%;"></textarea>
                        <label style="display:inline-flex;gap:6px;align-items:center;margin-top:4px;">
                            <input type="checkbox" id="use_rag"/> utiliser la base (RAG)
                        </label>
                <div class="row" style="margin-top:6px;">
                    <button onclick="ask()">Demander</button>
                    <small>via /ask</small>
                </div>
                <pre id="a"></pre>
            </div>
    </section>
  </div>

  <script>
    async function fetchText(url){ const r=await fetch(url); return r.ok ? r.text() : (r.status+" "+r.statusText); }
    async function fetchJSON(url){ const r=await fetch(url); return r.json(); }

    async function refreshAll(){ refreshLog(); refreshFiles(); refreshPrompt(); status(); }
    async function refreshLog(){
      const t = await fetchText('/api/logs?tail=500');
      document.getElementById('log').textContent = t || "(vide)";
    }
        async function refreshFiles(){
            const data = await fetchJSON('/api/files?limit=5');
      const el = document.getElementById('files');
      let html = '';
      if (data.eval.length){
        html += '<h3>Évaluations</h3><table><tr><th>Fichier</th><th>Score moyen</th></tr>';
        for(const row of data.eval){
          html += `<tr><td><a href="/api/file?path=${encodeURIComponent(row.path)}" target="_blank">${row.name}</a></td><td>${row.avg ?? ''}</td></tr>`;
        }
        html += '</table>';
                if (data.more_eval>0){ html += `<small>+ ${data.more_eval} de plus… <a href="#" onclick="showMore('eval')">voir tout</a></small>`; }
      }
      if (data.ab.length){
        html += '<h3>A/B tests</h3><table><tr><th>Fichier</th></tr>';
        for(const row of data.ab){
          html += `<tr><td><a href="/api/file?path=${encodeURIComponent(row.path)}" target="_blank">${row.name}</a></td></tr>`;
        }
        html += '</table>';
                if (data.more_ab>0){ html += `<small>+ ${data.more_ab} de plus… <a href="#" onclick="showMore('ab')">voir tout</a></small>`; }
      }
      el.innerHTML = html || '<small>Aucun CSV pour le moment.</small>';
    }
        async function showMore(kind){
            const data = await fetchJSON('/api/files?limit=1000');
            const el = document.getElementById('files');
            let html = '';
            if (data.eval.length){
                html += '<h3>Évaluations</h3><table><tr><th>Fichier</th><th>Score moyen</th></tr>';
                for(const row of data.eval){
                    html += `<tr><td><a href="/api/file?path=${encodeURIComponent(row.path)}" target="_blank">${row.name}</a></td><td>${row.avg ?? ''}</td></tr>`;
                }
                html += '</table>';
            }
            if (data.ab.length){
                html += '<h3>A/B tests</h3><table><tr><th>Fichier</th></tr>';
                for(const row of data.ab){
                    html += `<tr><td><a href="/api/file?path=${encodeURIComponent(row.path)}" target="_blank">${row.name}</a></td></tr>`;
                }
                html += '</table>';
            }
            el.innerHTML = html || '<small>Aucun CSV pour le moment.</small>';
        }
    async function refreshPrompt(){
      const t = await fetchText('/api/prompt/active');
      document.getElementById('prompt').textContent = t || "(vide)";
    }
    async function run(kind){
      document.getElementById('status').textContent = "Exécution: "+kind+"…";
      const r = await fetch('/api/run/'+kind, {method:'POST'});
      const j = await r.json();
      document.getElementById('status').textContent = j.ok ? "OK ("+j.seconds+'s)' : "Erreur";
      setTimeout(refreshAll, 1000);
    }
        async function ask(){
            const q = document.getElementById('q').value.trim();
            if(!q){ return; }
            document.getElementById('a').textContent = '…';
            const r = await fetch('/ask', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({question: q, use_rag: document.getElementById('use_rag').checked})
            });
            const j = await r.json();
            document.getElementById('a').textContent = j.answer || JSON.stringify(j);
        }
            async function learn(){
                const q = document.getElementById('q').value.trim();
                if(!q){ document.getElementById('status').textContent='Entrez une requête d\'apprentissage dans la zone ci-dessus.'; return; }
                document.getElementById('status').textContent='Apprentissage en cours…';
                const r= await fetch('/api/learn', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({query:q})});
                const j= await r.json();
                document.getElementById('status').textContent=`Appris ${j.count} page(s)`;
            }
    async function sched(action){
      const r = await fetch('/api/scheduler/'+action,{method:'POST'});
      const j = await r.json();
      document.getElementById('status').textContent = j.running ? "Auto: ON" : "Auto: OFF";
    }
    async function status(){
      const j = await (await fetch('/api/scheduler/status')).json();
        const intervalTxt = j.burst ? `${j.interval_seconds}s (burst)` : `${j.interval_minutes} min`;
        document.getElementById('status').textContent =
            `Auto: ${j.running?'ON':'OFF'} (intervalle ${intervalTxt})`;
    }

    refreshAll();
    setInterval(refreshLog, 2000);
  </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def root():
    # redirige vers le dashboard
    return DASH_HTML

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    return DASH_HTML

# -----------------------------------------------------------------------------
# API: logs / fichiers / prompt
# -----------------------------------------------------------------------------
@app.get("/api/logs", response_class=PlainTextResponse)
def api_logs(tail: int = 500):
    cfg = load_config()
    log_path = os.path.join(_abs(cfg["paths"]["logs_dir"]), "cron.log")
    if not os.path.exists(log_path):
        return "(pas de log pour l'instant)"
    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()[-tail:]
        return "".join(lines)
    except Exception as e:
        return f"(erreur lecture log: {e})"

@app.get("/api/files")
def api_files(limit: int = 5):
    os.makedirs(_abs("logs"), exist_ok=True)
    eval_files = sorted(glob.glob(str(Path(_abs("logs")) / "eval_*.csv")))
    ab_files   = sorted(glob.glob(str(Path(_abs("logs")) / "abtest_*.csv")))

    def parse_avg(path):
        avg = None
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.strip().startswith("avg_score"):
                        parts = line.strip().split(",")
                        if len(parts) > 1:
                            avg = parts[1]
        except:
            pass
        return avg

    eval_rows_all = [{"name": os.path.basename(p), "path": p, "avg": parse_avg(p)} for p in reversed(eval_files)]
    ab_rows_all   = [{"name": os.path.basename(p), "path": p} for p in reversed(ab_files)]
    return {
        "eval": eval_rows_all[:limit],
        "ab": ab_rows_all[:limit],
        "more_eval": max(0, len(eval_rows_all) - limit),
        "more_ab": max(0, len(ab_rows_all) - limit),
    }

@app.get("/api/file")
def api_file(path: str):
    if not os.path.exists(path):
        return PlainTextResponse("(fichier introuvable)", status_code=404)
    with open(path, "rb") as f:
        data = f.read()
    return Response(content=data, media_type="text/plain")

@app.get("/api/prompt/active", response_class=PlainTextResponse)
def api_prompt_active():
    cfg = load_config()
    return load_prompt(_abs(cfg["paths"]["active_prompt"]))

# Santé
@app.get("/health", response_class=PlainTextResponse)
def health():
    return "ok"

# -----------------------------------------------------------------------------
# API: exécuter les scripts depuis le serveur
# -----------------------------------------------------------------------------
def venv_python():
    # Trouver le binaire Python du venv (macOS/Linux/Windows) pour éviter les surprises
    candidates = [
        os.path.join(".venv", "bin", "python"),      # macOS/Linux
        os.path.join(".venv", "bin", "python3"),    # macOS/Linux
        os.path.join(".venv", "Scripts", "python.exe"),  # Windows
        os.path.join(".venv", "Scripts", "python"),      # Windows (msys)
    ]
    for exe in candidates:
        if os.path.exists(exe):
            return exe
    return sys.executable

def run_script(pyfile):
    t0 = datetime.now()
    script_path = str((BASE_DIR / pyfile).resolve()) if not os.path.isabs(pyfile) else pyfile
    timeout_s = int(load_config().get("scheduler", {}).get("script_timeout_seconds", 180))
    try:
        proc = subprocess.run(
            [venv_python(), script_path],
            capture_output=True,
            text=True,
            cwd=str(BASE_DIR),
            timeout=timeout_s,
        )
        ok = (proc.returncode == 0)
        out = (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired as e:
        ok = False
        out = f"[timeout] Script {pyfile} > {timeout_s}s\n" + (e.stdout or "") + (e.stderr or "")
    seconds = (datetime.now() - t0).total_seconds()
    # Append output to cron.log (utile si lancé depuis le dashboard / scheduler)
    os.makedirs(_abs("logs"), exist_ok=True)
    with open(os.path.join(_abs("logs"),"cron.log"), "a", encoding="utf-8") as log:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log.write(f"[WEB][{stamp}] RUN {pyfile}\n")
        log.write(out)
    return ok, seconds, out

@app.post("/api/run/evaluate")
def api_run_evaluate():
    ok, s, _ = run_script("scripts/evaluate.py")
    return {"ok": ok, "seconds": round(s,2)}

@app.post("/api/run/ab_test")
def api_run_ab():
    ok, s, _ = run_script("scripts/ab_test.py")
    return {"ok": ok, "seconds": round(s,2)}

@app.post("/api/run/promote")
def api_run_promote():
    ok, s, _ = run_script("scripts/promote.py")
    return {"ok": ok, "seconds": round(s,2)}

@app.post("/api/run/grow")
def api_run_grow():
    ok, s, _ = run_script("scripts/grow.py")
    return {"ok": ok, "seconds": round(s,2)}

@app.post("/api/run/self_update")
def api_run_self_update():
    ok, s, _ = run_script("scripts/self_update.py")
    return {"ok": ok, "seconds": round(s,2)}

class LearnReq(BaseModel):
    query: str

@app.post("/api/learn")
def api_learn(req: LearnReq):
    res = learn_from_web(req.query, results=3, store_path=_abs("data/rag.jsonl"))
    return res

# -----------------------------------------------------------------------------
# Scheduler continu (boucle auto)
# -----------------------------------------------------------------------------
_scheduler_task = None
_scheduler_lock = asyncio.Lock()

async def _cycle_once():
    # une itération: évaluer -> A/B -> promouvoir
    # Générer de nouveaux candidats à partir du prompt actif
    await asyncio.to_thread(run_script, "scripts/grow.py")
    # Évaluer
    await asyncio.to_thread(run_script, "scripts/evaluate.py")
    await asyncio.to_thread(run_script, "scripts/ab_test.py")
    await asyncio.to_thread(run_script, "scripts/promote.py")
    # Auto-update si activé dans la config (à la fin du cycle)
    try:
        cfg = load_config()
        if cfg.get("self_update", {}).get("enabled", False):
            await asyncio.to_thread(run_script, "scripts/self_update.py")
    except Exception as e:
        with open(os.path.join(_abs("logs"),"cron.log"), "a", encoding="utf-8") as log:
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log.write(f"[WEB][{stamp}] [self_update] ERREUR: {e}\n")

async def _scheduler_loop():
    cfg = load_config()
    sched = cfg.get("scheduler", {})
    burst = bool(sched.get("burst", False))
    interval_min = max(1, int(sched.get("interval_minutes", 60)))
    interval_sec = max(1, int(sched.get("interval_seconds", 5)))
    while True:
        async with _scheduler_lock:
            try:
                await _cycle_once()
            except Exception as e:
                os.makedirs("logs", exist_ok=True)
                with open(os.path.join("logs","cron.log"), "a", encoding="utf-8") as log:
                    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    log.write(f"[WEB][{stamp}] [scheduler] ERREUR: {e}\n")
        await asyncio.sleep(interval_sec if burst else interval_min * 60)

@app.on_event("startup")
async def _start_scheduler():
    global _scheduler_task
    cfg = load_config()
    if cfg.get("scheduler", {}).get("enabled", False):
        if _scheduler_task is None or _scheduler_task.done():
            _scheduler_task = asyncio.create_task(_scheduler_loop())

@app.on_event("shutdown")
async def _stop_scheduler():
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except asyncio.CancelledError:
            pass

@app.get("/api/scheduler/status")
def scheduler_status():
    cfg = load_config()
    running = bool(_scheduler_task and not _scheduler_task.done())
    return {
        "enabled_in_config": cfg.get("scheduler", {}).get("enabled", False),
        "running": running,
        "interval_minutes": cfg.get("scheduler", {}).get("interval_minutes", 60),
        "burst": cfg.get("scheduler", {}).get("burst", False),
        "interval_seconds": cfg.get("scheduler", {}).get("interval_seconds", 5),
    }

@app.post("/api/scheduler/start")
async def scheduler_start():
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        return {"ok": True, "running": True}
    _scheduler_task = asyncio.create_task(_scheduler_loop())
    return {"ok": True, "running": True}

@app.post("/api/scheduler/stop")
async def scheduler_stop():
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except asyncio.CancelledError:
            pass
    return {"ok": True, "running": False}
