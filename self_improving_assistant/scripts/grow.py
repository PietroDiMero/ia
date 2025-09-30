import os, yaml, glob, random, re
from datetime import datetime

"""
Crée automatiquement de nouveaux prompts candidats à partir du prompt actif
et des zones faibles observées (tags) dans le dataset.
Heuristique simple: injecter des consignes ciblées pour renforcer les domaines.
"""

def load_cfg():
    with open("configs/config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def read(path, default=""):
    try:
        return open(path, "r", encoding="utf-8").read()
    except:
        return default

def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def infer_weak_hints(tags_counts):
    # Retourne quelques messages d'amélioration en fonction des tags fréquents
    hints = []
    if tags_counts.get("macos") or tags_counts.get("cli"):
        hints.append("Quand la question concerne macOS/CLI, inclure la commande exacte avec options, et un exemple de sortie.")
    if tags_counts.get("git"):
        hints.append("Pour git, fournir la commande précise et rappeler les flags importants, avec une alternative si applicable.")
    if tags_counts.get("python"):
        hints.append("Pour Python, inclure la commande pip/venv et un snippet minimal exécutable.")
    if tags_counts.get("safety"):
        hints.append("Si la requête est risquée, proposer explicitement des alternatives sûres et prévenir des conséquences.")
    if tags_counts.get("network"):
        hints.append("Pour réseau, expliquer rapidement la signification des flags (ex: -c pour ping) et interpréter le résultat attendu.")
    return hints

def discover_recent_eval(logs_dir):
    files = sorted(glob.glob(os.path.join(logs_dir, "eval_*.csv")))
    return files[-1] if files else None

def main():
    cfg = load_cfg()
    active_path = cfg["paths"]["active_prompt"]
    prompts_dir = os.path.dirname(active_path)
    logs_dir = cfg["paths"]["logs_dir"]

    active = read(active_path)
    # Heuristique: on ne parse pas encore les scores par tag (CSV minimal), on part sur la couverture des tags du dataset
    # Amélioration future: stocker test_id->tags dans le CSV pour cibler précisément.
    # Ici, on ajoute des consignes génériques orientées domaines usuels.
    tags_counts = {"macos": 1, "cli": 1, "git": 1, "python": 1, "safety": 1, "network": 1}
    hints = infer_weak_hints(tags_counts)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffixes = [
        "mac_cli_focus",
        "git_safety_focus",
        "python_env_focus",
    ]
    created = []
    for suf in suffixes:
        extra = "\n\nAMÉLIORATIONS DEMANDÉES:\n- " + "\n- ".join(hints) + "\n"
        mutated = active.strip() + extra
        out_path = os.path.join(prompts_dir, f"auto_{suf}_{stamp}.txt")
        write(out_path, mutated)
        created.append(out_path)

    # Met à jour la liste des candidats dans la config ? Non (on garde la config statique)
    # Les A/B tests découvriront automatiquement les nouveaux fichiers en plus des candidats déclarés.
    print("Candidats générés:")
    for p in created:
        print(" -", p)

if __name__ == "__main__":
    main()
