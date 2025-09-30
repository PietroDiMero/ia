import os, json, yaml, datetime, csv, random

def load_cfg():
    with open("configs/config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def load_tests(path):
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]

def load_prompt(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def call_llm(prompt, question, provider="dummy", model=""):
    provider = (provider or "dummy").lower()
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
    # dummy fallback
    q = question.lower()
    if "riz" in q:
        return "En général, compte 60 à 80 g de riz cru par personne."
    if "ls" in q or "macos" in q:
        return "Utilise `ls -la` dans le terminal pour lister les fichiers (y compris cachés)."
    if "ram" in q:
        return "La RAM est une mémoire vive temporaire; le stockage (disque) conserve les données de façon plus permanente."
    return "Réponse générique pour test."

def score_answer(answer, expected_keywords, fail_keywords):
    a = answer.lower()
    hits = sum(1 for k in expected_keywords if k.lower() in a)
    for fk in fail_keywords:
        if fk.lower() in a:
            return 0.0, {"hits": hits, "fail": fk}
    max_hits = max(1, len(expected_keywords))
    return hits / max_hits, {"hits": hits}

def main():
    cfg = load_cfg()
    tests = load_tests(cfg["paths"]["tests_file"])
    sample_n = int(cfg.get("scheduler", {}).get("sample_tests", 0))
    if sample_n and sample_n < len(tests):
        tests = random.sample(tests, sample_n)
    # Découverte automatique de candidats: tous les .txt du dossier prompts sauf le prompt actif
    prompts_dir = os.path.dirname(cfg["paths"]["active_prompt"])
    active = os.path.abspath(cfg["paths"]["active_prompt"])
    cands_set = set(cfg["paths"].get("candidates", []) or [])
    import glob
    for p in glob.glob(os.path.join(prompts_dir, "*.txt")):
        if os.path.abspath(p) != active:
            cands_set.add(p)
    cands = sorted(cands_set)
    logs_dir = cfg["paths"]["logs_dir"]
    os.makedirs(logs_dir, exist_ok=True)

    results = []
    for cand in cands:
        prompt = load_prompt(cand)
        total = 0.0
        for t in tests:
            ans = call_llm(prompt, t["question"], cfg["provider"], cfg["model"])
            s, _ = score_answer(ans, t.get("expected_keywords", []), cfg["evaluation"]["fail_keywords"])
            total += s
        avg = total / max(1, len(tests))
        results.append((cand, avg))

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = os.path.join(logs_dir, f"abtest_{stamp}.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["candidate", "avg_score"])
        for c, s in results:
            w.writerow([c, s])

    # tri décroissant
    results.sort(key=lambda x: x[1], reverse=True)
    best = results[0]
    print("A/B terminé:", results)
    # écris le gagnant dans un fichier 'last_winner.txt'
    with open(os.path.join(logs_dir, "last_winner.txt"), "w", encoding="utf-8") as f:
        f.write(f"{best[0]},{best[1]:.4f}\n")

if __name__ == "__main__":
    main()
