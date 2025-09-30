import os, json, yaml, datetime, csv, re, random, concurrent.futures

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
    # scoring simple: +1 par mot-clé présent (normalisé)
    a = answer.lower()
    hits = sum(1 for k in expected_keywords if k.lower() in a)
    # fail si mots clefs interdits
    for fk in fail_keywords:
        if fk.lower() in a:
            return 0.0, {"hits": hits, "fail": fk}
    # normalisation 0..1
    max_hits = max(1, len(expected_keywords))
    return hits / max_hits, {"hits": hits}

def main():
    cfg = load_cfg()
    tests = load_tests(cfg["paths"]["tests_file"])
    # sampling optionnel
    sample_n = int(cfg.get("scheduler", {}).get("sample_tests", 0)) or int(cfg.get("evaluation", {}).get("daily_sample_size", 0) or 0)
    if sample_n and sample_n < len(tests):
        tests = random.sample(tests, sample_n)
    prompt = load_prompt(cfg["paths"]["active_prompt"])

    os.makedirs(cfg["paths"]["logs_dir"], exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_csv = os.path.join(cfg["paths"]["logs_dir"], f"eval_{stamp}.csv")

    def work(item):
        t = item
        ans = call_llm(prompt, t["question"], cfg["provider"], cfg["model"])
        s, _ = score_answer(ans, t.get("expected_keywords", []), cfg["evaluation"]["fail_keywords"])
        return t["id"], s, ans.replace("\n", " ")

    # Parallel workers
    pw = cfg.get("evaluation", {}).get("parallel_workers", "auto")
    if isinstance(pw, str) and pw.lower() == "auto":
        cpu = os.cpu_count() or 4
        workers = max(1, min(cpu-1, 24))
    else:
        try:
            workers = max(1, int(pw))
        except:
            workers = 4

    rows = []
    total = 0.0
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        for tid, s, ans in ex.map(work, tests):
            rows.append([tid, s, ans])
            total += s
    avg = total / max(1, len(tests))

    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["test_id", "score", "answer"])
        w.writerows(rows)
        w.writerow([])
        w.writerow(["avg_score", avg])

    print(f"Évaluation terminée. Score moyen = {avg:.3f}. Résultats: {out_csv}")

if __name__ == "__main__":
    main()
