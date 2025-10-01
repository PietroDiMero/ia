from fastapi import FastAPI, Response
import json
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel
import os, yaml, glob, subprocess, sys, asyncio
from datetime import datetime
from pathlib import Path
from .tools.web_rag import TinyRAG, learn_from_web

app = FastAPI()

# CORS (utile si la page est servie via un autre domaine/port ou pour du debug)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
"""
# Dashboard (HTML)
"""
DASH_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
    <title>Self-Improving Assistant — Dashboard</title>
  <style>
        :root { font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif; color-scheme: light dark; }
        body { margin: 0; padding: 16px; background: linear-gradient(180deg, rgba(127,127,127,0.06), transparent 180px); }
        header { display:flex; gap:16px; align-items:center; margin-bottom: 14px; flex-wrap: wrap; }
        h1 { margin:0; font-size: 20px; letter-spacing: 0.3px; }
        .btn { padding:8px 12px; border-radius:10px; border:1px solid #8884; cursor:pointer; background: #fff1; backdrop-filter: blur(6px); }
        .btn.primary { background: #4f46e5; color:#fff; border-color: #4f46e5; }
        .btn.warn { background: #d97706; color:#fff; border-color: #d97706; }
        .btn.ghost{ background: transparent; }
        .grid { display:grid; grid-template-columns: 1.2fr 1fr; gap:16px; }
        .card { border:1px solid #8883; border-radius:16px; padding:12px; background:rgba(127,127,127,0.06); box-shadow: 0 2px 12px rgba(0,0,0,.05); }
        h2,h3 { margin:0 0 8px; font-size: 15px; }
        pre { background:#0003; padding:8px; border-radius:8px; max-height:50vh; overflow:auto; white-space:pre-wrap; }
        table { width:100%; border-collapse: collapse; font-size: 13px; }
        th,td { border-bottom:1px solid #8882; padding:6px 8px; text-align:left; }
        small{opacity:.7}
        .row{display:flex; gap:10px; align-items:center; flex-wrap:wrap;}
        .stats { display:grid; grid-template-columns: repeat(4, 1fr); gap:10px; margin: 8px 0 12px; }
        .stat { background:#4f46e5; color:#fff; border-radius:12px; padding:10px; box-shadow: 0 2px 10px rgba(79,70,229,.3); }
        .stat h3{ margin:0; font-weight:600; font-size:12px; opacity:.9; }
        .stat .v{ font-size: 18px; font-weight:700; }
        .muted{ opacity:.75 }
        textarea { width:100%; padding:6px 8px; border-radius:8px; border:1px solid #8883; background: #fff1; }
        a { color: #2563eb; text-decoration: none; }
  </style>
</head>
<body>
  <header>
        <h1>Self-Improving Assistant — Dashboard</h1>
        <div class="row">
            <button class="btn" onclick="run('ingest')">🧠 Ingestion</button>
            <button class="btn" onclick="run('evaluate')">🧪 Évaluer</button>
            <button class="btn" onclick="run('ab_test')">A/B test</button>
            <button class="btn" onclick="run('promote')">⬆️ Promouvoir</button>
            <button class="btn" onclick="run('grow')">🌱 Générer candidats</button>
            <button class="btn" onclick="run('self_update')">🤖 Auto‑update code</button>
            <button class="btn primary" onclick="cycleNow()">⚡ Cycle maintenant</button>
            <button class="btn ghost" onclick="sched('start')">⏵ Auto ON</button>
            <button class="btn ghost" onclick="sched('stop')">⏸ Auto OFF</button>
            <button class="btn warn" onclick="turbo('on')">🚀 Turbo ON</button>
            <button class="btn ghost" onclick="turbo('off')">Turbo OFF</button>
            <small id="status" class="muted"></small>
        </div>
  </header>

    <section class="stats">
        <div class="stat"><h3>Auto</h3><div class="v" id="stat_auto">…</div><small id="stat_interval" class="muted"></small></div>
        <div class="stat"><h3>RAG docs</h3><div class="v" id="stat_docs">0</div><small id="stat_last_src" class="muted"></small></div>
        <div class="stat"><h3>Dernier ingest</h3><div class="v" id="stat_ingest">0</div><small id="stat_ingest_src" class="muted"></small></div>
        <div class="stat"><h3>Turbo</h3><div class="v" id="stat_turbo">OFF</div><small class="muted">Mode rapide</small></div>
    </section>

  <div class="grid">
    <section class="card">
      <h2>📜 Logs (cron.log)</h2>
      <div class="row">
                <button class="btn" onclick="refreshLog()">⟳ Actualiser</button>
                <small class="muted">auto-refresh toutes les 2s</small>
      </div>
      <pre id="log">Chargement…</pre>
    </section>

    <section class="card">
            <h2>🧪 Résultats & QA</h2>
      <div id="files"></div>
      <h3>Prompt actif</h3>
      <pre id="prompt">Chargement…</pre>
            <h3>Poser une question</h3>
            <div>
                                                <textarea id="q" rows="3"></textarea>
                        <label style="display:inline-flex;gap:6px;align-items:center;margin-top:4px;">
                            <input type="checkbox" id="use_rag"/> utiliser la base (RAG)
                        </label>
                <div class="row" style="margin-top:6px;">
                                        <button class="btn" onclick="ask()">Demander</button>
                                        <small class="muted">via /ask</small>
                </div>
                <pre id="a"></pre>
            </div>
    </section>
  </div>

  <script>
        function setStatus(msg){ document.getElementById('status').textContent = msg; }
                async function fetchText(url){ try{ const r=await fetch(url); return r.ok ? r.text() : (r.status+" "+r.statusText);}catch(e){ setStatus('Erreur réseau: '+e); return ''; } }
                async function fetchJSON(url, init){ try{ const r=await fetch(url, init); if(!r.ok){ setStatus('Erreur HTTP '+r.status); return {}; } return await r.json(); }catch(e){ setStatus('Erreur réseau: '+e); return {}; } }

        async function refreshAll(){ try { await refreshLog(); await refreshFiles(); await refreshPrompt(); await refreshStatus(); await refreshRagStats(); await refreshIngest(); } catch(e){ setStatus('Erreur chargement: '+e); } }
    async function refreshLog(){
      const t = await fetchText('/api/logs?tail=500');
      document.getElementById('log').textContent = t || "(vide)";
    }
        async function refreshFiles(){
            const data = await fetchJSON('/api/files?limit=5');
      const el = document.getElementById('files');
      let html = '';
            if (data.eval?.length){
        html += '<h3>Évaluations</h3><table><tr><th>Fichier</th><th>Score moyen</th></tr>';
        for(const row of data.eval){
          html += `<tr><td><a href="/api/file?path=${encodeURIComponent(row.path)}" target="_blank">${row.name}</a></td><td>${row.avg ?? ''}</td></tr>`;
        }
        html += '</table>';
                                if (data.more_eval>0){ html += `<small class="muted">+ ${data.more_eval} de plus… <a href="#" onclick="showMore('eval')">voir tout</a></small>`; }
      }
            if (data.ab?.length){
        html += '<h3>A/B tests</h3><table><tr><th>Fichier</th></tr>';
        for(const row of data.ab){
          html += `<tr><td><a href="/api/file?path=${encodeURIComponent(row.path)}" target="_blank">${row.name}</a></td></tr>`;
        }
        html += '</table>';
                                if (data.more_ab>0){ html += `<small class="muted">+ ${data.more_ab} de plus… <a href="#" onclick="showMore('ab')">voir tout</a></small>`; }
      }
            el.innerHTML = html || '<small class="muted">Aucun CSV pour le moment.</small>';
    }
        async function showMore(kind){
            const data = await fetchJSON('/api/files?limit=1000');
            const el = document.getElementById('files');
            let html = '';
                        if (data.eval?.length){
                html += '<h3>Évaluations</h3><table><tr><th>Fichier</th><th>Score moyen</th></tr>';
                for(const row of data.eval){
                    html += `<tr><td><a href="/api/file?path=${encodeURIComponent(row.path)}" target="_blank">${row.name}</a></td><td>${row.avg ?? ''}</td></tr>`;
                }
                html += '</table>';
            }
                        if (data.ab?.length){
                html += '<h3>A/B tests</h3><table><tr><th>Fichier</th></tr>';
                for(const row of data.ab){
                    html += `<tr><td><a href="/api/file?path=${encodeURIComponent(row.path)}" target="_blank">${row.name}</a></td></tr>`;
                }
                html += '</table>';
            }
                        el.innerHTML = html || '<small class="muted">Aucun CSV pour le moment.</small>';
        }
    async function refreshPrompt(){
      const t = await fetchText('/api/prompt/active');
      document.getElementById('prompt').textContent = t || "(vide)";
    }
        async function run(kind){
            setStatus("Exécution: "+kind+"…");
            try{
                                const j = await fetchJSON('/api/run/'+kind, {method:'POST'});
                setStatus(j.ok ? "OK ("+j.seconds+'s)' : "Erreur");
            }catch(e){ setStatus('Erreur: '+e); }
            setTimeout(refreshAll, 1000);
        }
        async function ask(){
            const q = document.getElementById('q').value.trim();
            if(!q){ return; }
            document.getElementById('a').textContent = '…';
            try{
                            const j = await fetchJSON('/ask', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({question: q, use_rag: document.getElementById('use_rag').checked}) });
              document.getElementById('a').textContent = j.answer || JSON.stringify(j);
            }catch(e){ document.getElementById('a').textContent = 'Erreur: '+e; setStatus('Erreur: '+e); }
        }
                        async function learn(){
                const q = document.getElementById('q').value.trim();
                if(!q){ document.getElementById('status').textContent="Entrez une requête d'apprentissage dans la zone ci-dessus."; return; }
                document.getElementById('status').textContent='Apprentissage en cours…';
                                try{
                                                                        const j= await fetchJSON('/api/learn', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({query:q})});
                                    document.getElementById('status').textContent=`Appris ${j.count} page(s)`;
                                }catch(e){ setStatus('Erreur: '+e); }
            }
    async function sched(action){
            try{
                                const j = await fetchJSON('/api/scheduler/'+action,{method:'POST'});
                document.getElementById('status').textContent = j.running ? "Auto: ON" : "Auto: OFF";
            }catch(e){ setStatus('Erreur: '+e); }
    }
    async function refreshStatus(){
            try{
                                const j = await fetchJSON('/api/scheduler/status');
                                const intervalTxt = j.burst ? `${j.interval_seconds}s (burst)` : `${j.interval_minutes} min`;
                                document.getElementById('status').textContent = `Auto: ${j.running?'ON':'OFF'} (intervalle ${intervalTxt})`;
                                document.getElementById('stat_auto').textContent = j.running?'ON':'OFF';
                                document.getElementById('stat_interval').textContent = `intervalle ${intervalTxt}`;
                                document.getElementById('stat_turbo').textContent = j.turbo ? 'ON' : 'OFF';
            }catch(e){ setStatus('Erreur: '+e); }
    }
        async function refreshRagStats(){ try{ const j = await fetchJSON('/api/rag/stats'); document.getElementById('stat_docs').textContent = j.count ?? 0; document.getElementById('stat_last_src').textContent = j.last_source ? ('dernier: '+j.last_source) : ''; }catch(e){} }
        async function refreshIngest(){ try{ const j = await fetchJSON('/api/ingest/last'); const total = (j.search?.learned_chunks||0) + (j.rss?.learned_chunks||0); document.getElementById('stat_ingest').textContent = total; const srcs = Math.max(j.search?.unique_sources||0, j.rss?.unique_sources||0); document.getElementById('stat_ingest_src').textContent = srcs ? (srcs+ ' source(s)') : ''; }catch(e){} }
        async function cycleNow(){ setStatus('Cycle en cours…'); const j = await fetchJSON('/api/scheduler/cycle_now', {method:'POST'}); setStatus(j.ok? 'Cycle OK' : 'Erreur'); setTimeout(refreshAll, 1200); }
        async function turbo(mode){ const j = await fetchJSON('/api/settings/turbo?mode='+mode, {method:'POST'}); setStatus(j.ok? ('Turbo '+mode.toUpperCase()) : 'Erreur'); await refreshStatus(); }

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

@app.post("/api/run/ingest")
def api_run_ingest():
    ok, s, _ = run_script("scripts/ingest.py")
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
_turbo = False

async def _cycle_once():
    # une itération: évaluer -> A/B -> promouvoir
    # Apprentissage web (si activé via config RAG; le script est no-op si rien à faire)
    await asyncio.to_thread(run_script, "scripts/ingest.py")
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
    # recharge la config à chaque itération pour prendre en compte les réglages dynamiques
    while True:
        cfg = load_config()
        sched = cfg.get("scheduler", {})
        burst = bool(sched.get("burst", False))
        interval_min = max(1, int(sched.get("interval_minutes", 60)))
        interval_sec = max(1, int(sched.get("interval_seconds", 5)))
        if _turbo:
            burst = True
            interval_sec = min(10, interval_sec)
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
        "turbo": _turbo,
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

# Actions avancées
@app.post("/api/scheduler/cycle_now")
async def api_cycle_now():
    async with _scheduler_lock:
        try:
            await _cycle_once()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

def _save_config(cfg: dict):
    with open(_abs("configs/config.yaml"), "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)

@app.post("/api/settings/turbo")
def api_turbo(mode: str = "on"):
    global _turbo
    _turbo = (mode.lower() == "on")
    try:
        cfg = load_config()
        sec = cfg.get("rag", {}).get("security", {})
        if _turbo:
            sec["max_pages_per_domain"] = max(int(sec.get("max_pages_per_domain", 5)), 12)
            sec["rate_limit_per_domain"] = max(int(sec.get("rate_limit_per_domain", 6)), 20)
        else:
            sec["max_pages_per_domain"] = 5
            sec["rate_limit_per_domain"] = 6
        cfg.setdefault("rag", {})["security"] = sec
        sched = cfg.get("scheduler", {})
        if _turbo:
            sched["burst"] = True
            sched["interval_seconds"] = min(int(sched.get("interval_seconds", 60)), 10)
        cfg["scheduler"] = sched
        _save_config(cfg)
    except Exception:
        pass
    return {"ok": True, "turbo": _turbo}

@app.get("/api/rag/stats")
def api_rag_stats():
    path = _abs("data/rag.jsonl")
    count = 0
    last_source = None
    last_ts = 0
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line: continue
                    count += 1
                    try:
                        obj = json.loads(line)
                        ts = float(obj.get("ts") or 0)
                        if ts >= last_ts:
                            last_ts = ts
                            meta = obj.get("meta") or {}
                            last_source = meta.get("source")
                    except:
                        pass
        except Exception:
            pass
    return {"count": count, "last_source": last_source, "last_ts": last_ts}

@app.get("/api/ingest/last")
def api_ingest_last():
    cfg = load_config()
    p = os.path.join(_abs(cfg["paths"]["logs_dir"]), "ingest_last.json")
    if not os.path.exists(p):
        return {"search": {"learned_chunks": 0, "unique_sources": 0}, "rss": {"learned_chunks": 0, "unique_sources": 0}}
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return {"error": str(e)}