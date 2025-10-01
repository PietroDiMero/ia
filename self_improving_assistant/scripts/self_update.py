import os, json, yaml, subprocess, sys, shutil, datetime, tempfile

"""
Tentative d'auto-mise à jour du code:
- Demande au LLM de proposer un petit patch (diff unifié) dans des zones autorisées
- Applique le patch en local (dry-run possible)
- Lance evaluate/ab_test/promote et mesure le gain
- Si pas de gain, revert
"""

def load_cfg():
    with open("configs/config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def venv_python():
    candidates = [
        os.path.join(".venv","bin","python"),
        os.path.join(".venv","bin","python3"),
        os.path.join(".venv","Scripts","python.exe"),
        os.path.join(".venv","Scripts","python"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return sys.executable

def run(cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)

def last_eval_score(logs_dir):
    import glob
    files = sorted(glob.glob(os.path.join(logs_dir, "eval_*.csv")))
    if not files:
        return 0.0
    score = 0.0
    with open(files[-1], "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.strip().startswith("avg_score"):
                parts = line.split(",")
                if len(parts)>1:
                    try:
                        score = float(parts[1])
                    except:
                        pass
    return score

def call_llm_system(cfg, sys_prompt, user_prompt):
    # Utilise le provider spécifique à self_update s'il est défini (sinon fallback global)
    su = cfg.get("self_update", {}) or {}
    provider = (su.get("provider") or cfg.get("provider") or "dummy").lower()
    model = su.get("model") or cfg.get("model") or "gpt-4o-mini"
    if provider == "openai":
        try:
            from openai import OpenAI
            client = OpenAI()
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role":"system","content": sys_prompt},
                    {"role":"user","content": user_prompt},
                ],
                temperature=0,
                max_tokens=1200,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as e:
            return f"[openai error] {e}"
    return ""  # autres providers à ajouter si souhaité

def apply_unified_patch(patch_text, allow_paths, max_files=3):
    """Applique un diff unifié minimaliste via 'patch' si dispo, sinon best effort.
    Par simplicité et robustesse, on crée un temp repo et on écrit directement les fichiers si le patch est annoté '*** Update File:' (format interne déjà utilisé).
    """
    # Supporte notre format interne si présent, sinon noop.
    blocks = [b for b in patch_text.split("*** Update File:") if b.strip()]
    changed = []
    for b in blocks[:max_files]:
        header, *rest = b.split("\n", 1)
        path = header.strip()
        # sécurité chemins
        if not any(path.startswith(ap) for ap in allow_paths):
            continue
        if not rest:
            continue
        content = rest[0]
        try:
            with open(path, "r", encoding="utf-8") as f:
                old = f.read()
        except FileNotFoundError:
            old = ""
        # naïf: si contient '->' on suppose remplacement complet
        if "->" in header:
            # format non supporté ici
            continue
        # Heuristique: si le patch contient une ligne '+++ NEW CONTENT' on remplace tout
        if "+++ NEW CONTENT" in content:
            new = content.split("+++ NEW CONTENT",1)[1]
        else:
            # fallback: remplacement total (dans un vrai système, parser le diff)
            new = content
        with open(path, "w", encoding="utf-8") as f:
            f.write(new)
        changed.append(path)
    return changed

def main():
    cfg = load_cfg()
    su = cfg.get("self_update", {})
    if not su.get("enabled", False):
        print("Self-update désactivé dans config.")
        return
    allow_paths = su.get("allow_paths", ["app/","scripts/","prompts/"])
    max_files = int(su.get("max_files", 3))
    dry_run = bool(su.get("dry_run", False))
    explain = bool(su.get("explain", True))

    logs_dir = cfg["paths"]["logs_dir"]
    os.makedirs(logs_dir, exist_ok=True)
    before = last_eval_score(logs_dir)

    # Contexte minimal pour le LLM: objectifs et contraintes
    sys_prompt = (
        "Tu es un agent d'amélioration de code. Propose un petit patch pour améliorer les scores d'évaluation. "
        "Contraintes: sécurité d'abord, pas de suppression de fonctionnalités utiles, pas de mouvements de fichiers massifs. "
        "Modifie au plus " + str(max_files) + " fichier(s) dans les chemins autorisés. "
        "Propose un patch au format '*** Update File: <path>\n+++ NEW CONTENT\n<contenu complet>' pour chaque fichier."
    )
    user_prompt = (
        "Objectif: augmenter avg_score > " + str(su.get("min_gain",0.01)) + " par rapport à l'actuel.\n"
        "Contexte: nous avons des tests variés (macOS/CLI, git, python, safety).\n"
        "Idées: améliorer prompts, ajouter détails dans réponses RAG, ajuster sampling/timeouts.\n"
        "Propose un patch minimal et sûr."
    )

    patch = call_llm_system(cfg, sys_prompt, user_prompt)
    if not patch:
        print("Aucun patch proposé par le LLM.")
        return

    # Sauvegarde pour audit
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    note_path = os.path.join(logs_dir, f"self_update_{stamp}.txt")
    if explain:
        with open(note_path, "w", encoding="utf-8") as f:
            f.write(patch)

    if dry_run:
        print("Dry-run: patch non appliqué. Voir:", note_path)
        return

    # Snapshot pour rollback
    backup_dir = os.path.join(logs_dir, f"backup_{stamp}")
    os.makedirs(backup_dir, exist_ok=True)
    for p in allow_paths:
        if os.path.exists(p):
            shutil.copytree(p, os.path.join(backup_dir, p.strip("/")), dirs_exist_ok=True)

    changed = apply_unified_patch(patch, allow_paths, max_files=max_files)
    if not changed:
        print("Patch non appliqué (aucun fichier autorisé modifié).")
        return

    # Évaluer après patch
    py = venv_python()
    run([py, "scripts/evaluate.py"]).check_returncode()
    after = last_eval_score(logs_dir)
    gain = after - before
    print(f"Score avant: {before:.3f}, après: {after:.3f}, gain: {gain:.3f}")

    min_gain = float(su.get("min_gain", 0.01))
    if gain >= min_gain:
        print("Patch accepté.")
    else:
        print("Gain insuffisant, rollback…")
        # Rollback
        for p in allow_paths:
            src = os.path.join(backup_dir, p.strip("/"))
            if os.path.exists(src):
                shutil.copytree(src, p, dirs_exist_ok=True)

if __name__ == "__main__":
    main()
