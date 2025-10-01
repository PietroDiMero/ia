import os, re, json, time, hashlib, socket, ipaddress
from typing import List, Dict, Tuple
import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
from rank_bm25 import BM25Okapi
from urllib.parse import urlparse, urljoin
from urllib import robotparser
import yaml


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


def _get_domain(url: str) -> str:
    try:
        return urlparse(url).hostname or ""
    except:
        return ""

def _is_private_ip(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
        for fam, _, _, _, sockaddr in infos:
            ip = sockaddr[0]
            try:
                if ipaddress.ip_address(ip).is_private:
                    return True
            except ValueError:
                continue
    except Exception:
        return False
    return False

_robots_cache: Dict[str, robotparser.RobotFileParser] = {}

def _robots_allowed(sec: dict, url: str, ua: str) -> bool:
    if not sec.get("respect_robots", True):
        return True
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if not host:
        return False
    base = f"{parsed.scheme}://{host}"
    if host not in _robots_cache:
        rp = robotparser.RobotFileParser()
        try:
            rp.set_url(urljoin(base, "/robots.txt"))
            rp.read()
        except Exception:
            rp = None
        _robots_cache[host] = rp
    rp = _robots_cache.get(host)
    if not rp:
        return True
    try:
        return rp.can_fetch(ua, url)
    except Exception:
        return True

def _is_allowed_url(sec: dict, url: str) -> Tuple[bool, str]:
    parsed = urlparse(url)
    scheme = (parsed.scheme or '').lower()
    host = (parsed.hostname or '').lower()
    if scheme not in (sec.get("allowed_schemes") or ["http","https"]):
        return False, f"scheme_not_allowed:{scheme}"
    if not host:
        return False, "no_host"
    for bd in (sec.get("block_domains") or []):
        if host == bd.lower() or host.endswith("."+bd.lower()):
            return False, f"blocked_domain:{host}"
    allow = [d.lower() for d in (sec.get("allow_domains") or [])]
    if allow:
        if not any(host == d or host.endswith("."+d) for d in allow):
            return False, f"not_in_allowlist:{host}"
    if sec.get("disallow_private_ips", True) and _is_private_ip(host):
        return False, f"private_ip:{host}"
    return True, "ok"

def _redact(text: str, patterns: List[str]) -> str:
    if not patterns:
        return text
    out = text
    for p in patterns:
        try:
            out = re.sub(p, "[REDACTED]", out)
        except re.error:
            continue
    return out

def _openai_summarize(cfg: dict, text: str) -> str:
    rag_sum = cfg.get("rag", {}).get("summarize", {})
    if not rag_sum.get("enabled", False):
        return ""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return ""
    try:
        from openai import OpenAI
        client = OpenAI()
        prompt = rag_sum.get("prompt") or "Résumé"
        model = rag_sum.get("model") or cfg.get("model") or "gpt-4o-mini"
        max_tokens = int(rag_sum.get("max_tokens", 600))
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role":"system","content": prompt},
                {"role":"user","content": text},
            ],
            temperature=0,
            max_tokens=max_tokens,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception:
        return ""

def fetch_page(url: str, sec: dict) -> Tuple[str, str]:
    ok, reason = _is_allowed_url(sec, url)
    if not ok:
        return "", reason
    ua = sec.get("user_agent", "SelfImprover/1.0")
    if not _robots_allowed(sec, url, ua):
        return "", "robots_disallow"
    try:
        r = requests.get(url, timeout=int(sec.get("timeout_seconds", 20)), headers={"User-Agent": ua})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        for s in soup(["script", "style", "noscript"]):
            s.decompose()
        text = "\n".join(t.strip() for t in soup.get_text("\n").splitlines() if t.strip())
        return text[: int(sec.get("max_chars_per_page", 20000))], "ok"
    except Exception as e:
        return "", f"fetch_error:{e}"


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


def _load_cfg() -> dict:
    # recherche relative depuis app/ -> racine projet
    here = os.path.dirname(os.path.dirname(__file__))  # app/
    root = os.path.dirname(here)  # project/
    cfg_path = os.path.join(root, "configs", "config.yaml")
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        return {}

def learn_from_web(query: str, results: int = 3, store_path: str = "data/rag.jsonl") -> Dict:
    cfg = _load_cfg()
    sec = (cfg.get("rag", {}) or {}).get("security", {})
    sum_cfg = (cfg.get("rag", {}) or {}).get("summarize", {})
    rag = TinyRAG(store_path)
    found = web_search(query, max_results=results)
    kept = []
    last_req: Dict[str, float] = {}
    domain_counts: Dict[str, int] = {}
    redact_patterns = (sec.get("redact_patterns") or [])
    for r in found:
        url = r.get("href")
        if not url:
            continue
        domain = _get_domain(url)
        if domain_counts.get(domain, 0) >= int(sec.get("max_pages_per_domain", 5)):
            continue
        # simple rate limiting
        rpm = int(sec.get("rate_limit_per_domain", 6))
        spacing = 60.0 / max(1, rpm)
        t0 = last_req.get(domain, 0.0)
        delay = t0 + spacing - time.time()
        if delay > 0:
            time.sleep(min(delay, 5.0))
        last_req[domain] = time.time()

        text, reason = fetch_page(url, sec)
        if not text:
            continue
        domain_counts[domain] = domain_counts.get(domain, 0) + 1
        text = _redact(text, redact_patterns)
        if (sum_cfg.get("enabled", False)):
            max_in = int(sum_cfg.get("max_input_chars", 8000))
            summary = _openai_summarize(cfg, text[:max_in])
            if summary:
                if rag.upsert(summary, {"source": url, "title": r.get("title"), "kind": "learn_summary", "q": query, "raw_len": len(text)}):
                    kept.append(url)
                if bool(sum_cfg.get("store_raw", False)):
                    rag.upsert(text[:2000], {"source": url, "title": r.get("title"), "kind": "learn_raw_first2k", "q": query})
            else:
                if rag.upsert(text, {"source": url, "title": r.get("title"), "kind": "learn", "q": query}):
                    kept.append(url)
        else:
            if rag.upsert(text, {"source": url, "title": r.get("title"), "kind": "learn", "q": query}):
                kept.append(url)
    return {"learned": kept, "count": len(kept)}
