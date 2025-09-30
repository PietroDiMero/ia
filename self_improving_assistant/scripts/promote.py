import os, yaml, time

def load_cfg():
    with open("configs/config.yaml","r",encoding="utf-8") as f:
        return yaml.safe_load(f)

def read_last_winner(logs_dir):
    p = os.path.join(logs_dir, "last_winner.txt")
    if not os.path.exists(p): return None, None
    cand, score = open(p,"r",encoding="utf-8").read().strip().split(",")
    return cand, float(score)

def last_promotion_ts(logs_dir):
    p = os.path.join(logs_dir, "last_promotion.ts")
    return float(open(p).read()) if os.path.exists(p) else 0.0

def write_promotion_ts(logs_dir):
    with open(os.path.join(logs_dir,"last_promotion.ts"),"w") as f:
        f.write(str(time.time()))

def main():
    cfg = load_cfg()
    logs_dir = cfg["paths"]["logs_dir"]
    os.makedirs(logs_dir, exist_ok=True)
    cand, cand_score = read_last_winner(logs_dir)
    if not cand:
        print("Aucun résultat A/B.")
        return

    min_gain = float(cfg["scheduler"].get("min_promotion_gain", 0.01))
    cooldown = int(cfg["scheduler"].get("cooldown_minutes", 30)) * 60
    now = time.time()
    if now - last_promotion_ts(logs_dir) < cooldown:
        print("Cooldown: pas de promotion.")
        return

    # Lire score actuel (dernier eval CSV) pour comparer
    import glob
    eval_files = sorted(glob.glob(os.path.join(logs_dir, "eval_*.csv")))
    active_score = 0.0
    if eval_files:
        with open(eval_files[-1], "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if line.strip().startswith("avg_score"):
                    parts = line.strip().split(",")
                    if len(parts)>1: active_score = float(parts[1])

    gain = cand_score - active_score
    if gain >= min_gain:
        with open(cand, "r", encoding="utf-8") as src:
            content = src.read()
        with open(cfg["paths"]["active_prompt"], "w", encoding="utf-8") as dst:
            dst.write(content)
        write_promotion_ts(logs_dir)
        print(f"PROMOTION: {cand} (score={cand_score:.3f}, gain={gain:.3f})")
    else:
        print(f"Pas de promotion (gain {gain:.3f} < {min_gain:.3f}).")

if __name__ == "__main__":
    main()
