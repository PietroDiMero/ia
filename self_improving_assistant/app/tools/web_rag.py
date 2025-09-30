import os, re, json, time, hashlib
from typing import List, Dict
import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
from rank_bm25 import BM25Okapi


def web_search(query: str, max_results: int = 5) -> List[Dict]:
    results = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=max_results):
            results.append({
                "title": r.get("title"),
                "href": r.get("href"),
                "body": r.get("body"),
            })
    return results


def fetch_page(url: str, timeout: int = 20) -> str:
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "SelfImprover/1.0"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        for s in soup(["script", "style", "noscript"]):
            s.decompose()
        text = "\n".join(t.strip() for t in soup.get_text("\n").splitlines() if t.strip())
        return text[:20000]  # limite simple
    except Exception as e:
        return f"[fetch_error] {e}"


class TinyRAG:
    """
    Très petit RAG local: conserve des documents en JSONL et fait une retrieval BM25.
    """
    def __init__(self, store_path: str = "data/rag.jsonl"):
        self.store_path = store_path
        os.makedirs(os.path.dirname(store_path), exist_ok=True)
        self.docs = []
        self._load()
        self._bm25 = None
        self._reindex()

    def _load(self):
        if not os.path.exists(self.store_path):
            return
        with open(self.store_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    self.docs.append(json.loads(line))
                except:
                    pass

    def _save_one(self, doc: Dict):
        with open(self.store_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")

    def _reindex(self):
        if not self.docs:
            self._bm25 = None
            return
        tokenized = [d.get("text", "").lower().split() for d in self.docs]
        self._bm25 = BM25Okapi(tokenized)

    def upsert(self, text: str, meta: Dict):
        h = hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()
        if any(d.get("id") == h for d in self.docs):
            return
        doc = {"id": h, "text": text, "meta": meta, "ts": time.time()}
        self.docs.append(doc)
        self._save_one(doc)
        self._reindex()

    def query(self, q: str, top_k: int = 3) -> List[Dict]:
        if not self._bm25:
            return []
        scores = self._bm25.get_scores(q.lower().split())
        ranked = sorted(zip(self.docs, scores), key=lambda x: x[1], reverse=True)
        return [{"text": d["text"], "score": s, "meta": d["meta"]} for d, s in ranked[:top_k]]


def learn_from_web(query: str, results: int = 3, store_path: str = "data/rag.jsonl") -> Dict:
    rag = TinyRAG(store_path)
    found = web_search(query, max_results=results)
    kept = []
    for r in found:
        url = r.get("href")
        if not url:
            continue
        text = fetch_page(url)
        if text and not text.startswith("[fetch_error]"):
            rag.upsert(text, {"source": url, "title": r.get("title")})
            kept.append(url)
    return {"learned": kept, "count": len(kept)}
