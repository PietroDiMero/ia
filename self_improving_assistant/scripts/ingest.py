import os, re, json, time, math, hashlib, yaml, socket, ipaddress
from typing import List, Dict, Tuple
import requests
import feedparser
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
from urllib.parse import urlparse, urljoin
from urllib import robotparser


def load_cfg():
	with open("configs/config.yaml", "r", encoding="utf-8") as f:
		return yaml.safe_load(f)


def web_search(query: str, max_results: int = 5) -> List[Dict]:
	out = []
	with DDGS() as ddgs:
		for r in ddgs.text(query, max_results=max_results):
			out.append({"title": r.get("title"), "href": r.get("href"), "body": r.get("body")})
	return out


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

def _is_allowed_url(sec: dict, url: str) -> Tuple[bool, str]:
	parsed = urlparse(url)
	scheme = (parsed.scheme or '').lower()
	host = (parsed.hostname or '').lower()
	if scheme not in (sec.get("allowed_schemes") or ["http","https"]):
		return False, f"scheme_not_allowed:{scheme}"
	if not host:
		return False, "no_host"
	# block list
	for bd in (sec.get("block_domains") or []):
		if host == bd.lower() or host.endswith("."+bd.lower()):
			return False, f"blocked_domain:{host}"
	# allow list (if non-empty)
	allow = [d.lower() for d in (sec.get("allow_domains") or [])]
	if allow:
		if not any(host == d or host.endswith("."+d) for d in allow):
			return False, f"not_in_allowlist:{host}"
	# private IPs
	if sec.get("disallow_private_ips", True) and _is_private_ip(host):
		return False, f"private_ip:{host}"
	return True, "ok"

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
			# si robots introuvable: prudence mais autoriser
			rp = None
		_robots_cache[host] = rp
	rp = _robots_cache.get(host)
	if not rp:
		return True
	try:
		return rp.can_fetch(ua, url)
	except Exception:
		return True

def _rate_limit_wait(domain: str, sec: dict, last_req: Dict[str, float]):
	rpm = int(sec.get("rate_limit_per_domain", 6))
	spacing = 60.0 / max(1, rpm)
	t0 = last_req.get(domain, 0.0)
	delay = t0 + spacing - time.time()
	if delay > 0:
		time.sleep(min(delay, 5.0))
	last_req[domain] = time.time()

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
	if not text:
		return ""
	rag_sum = cfg.get("rag", {}).get("summarize", {})
	if not rag_sum.get("enabled", False):
		return ""
	provider = (rag_sum.get("provider") or "").lower()
	if provider != "openai":
		return ""
	api_key = os.getenv("OPENAI_API_KEY")
	if not api_key:
		return ""  # pas de clé => pas de résumé
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
	# returns (text_or_error, reason_or_ok)
	ok, reason = _is_allowed_url(sec, url)
	if not ok:
		return "", reason
	ua = sec.get("user_agent", "SIA-Ingest/1.0")
	if not _robots_allowed(sec, url, ua):
		return "", "robots_disallow"
	try:
		r = requests.get(url, timeout=int(sec.get("timeout_seconds", 20)), headers={"User-Agent": ua})
		r.raise_for_status()
		soup = BeautifulSoup(r.text, "lxml")
		for s in soup(["script", "style", "noscript"]):
			s.decompose()
		text = "\n".join(t.strip() for t in soup.get_text("\n").splitlines() if t.strip())
		text = text[: int(sec.get("max_chars_per_page", 20000))]
		return text, "ok"
	except Exception as e:
		return "", f"fetch_error:{e}"


def split_chunks(text: str, max_tokens: int = 800) -> List[str]:
	# split naive par paragraphes/phrases, approx tokens=words
	words = text.split()
	chunks = []
	for i in range(0, len(words), max_tokens):
		chunk = " ".join(words[i:i+max_tokens])
		if chunk:
			chunks.append(chunk)
	return chunks


class TinyRAG:
	def __init__(self, store_path: str = "data/rag.jsonl"):
		from rank_bm25 import BM25Okapi
		self.store_path = store_path
		os.makedirs(os.path.dirname(store_path), exist_ok=True)
		self.docs = []
		self._bm25 = None
		self._load()
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
		from rank_bm25 import BM25Okapi
		if not self.docs:
			self._bm25 = None
			return
		tokenized = [d.get("text", "").lower().split() for d in self.docs]
		self._bm25 = BM25Okapi(tokenized)

	def upsert(self, text: str, meta: Dict):
		h = hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()
		if any(d.get("id") == h for d in self.docs):
			return False
		doc = {"id": h, "text": text, "meta": meta, "ts": time.time()}
		self.docs.append(doc)
		self._save_one(doc)
		self._reindex()
		return True


def ingest_from_search(cfg: dict, queries: List[str], max_results: int, store: TinyRAG) -> Dict:
	learned = 0
	sources = []
	sec = (cfg.get("rag", {}) or {}).get("security", {})
	last_req: Dict[str, float] = {}
	domain_counts: Dict[str, int] = {}
	redact_patterns = (sec.get("redact_patterns") or [])
	sum_cfg = (cfg.get("rag", {}) or {}).get("summarize", {})
	for q in queries:
		for r in web_search(q, max_results=max_results):
			url = r.get("href")
			if not url:
				continue
			domain = _get_domain(url)
			if domain_counts.get(domain, 0) >= int(sec.get("max_pages_per_domain", 5)):
				continue
			_rate_limit_wait(domain, sec, last_req)
			text, reason = fetch_page(url, sec)
			if not text:
				continue
			domain_counts[domain] = domain_counts.get(domain, 0) + 1
			text = _redact(text, redact_patterns)
			if (cfg.get("rag", {}).get("summarize", {}).get("enabled", False)):
				max_in = int(sum_cfg.get("max_input_chars", 8000))
				summary = _openai_summarize(cfg, text[:max_in])
				if summary:
					if store.upsert(summary, {"source": url, "title": r.get("title"), "kind": "search_summary", "q": q, "raw_len": len(text)}):
						learned += 1
						sources.append(url)
					# si store_raw=True, on stocke aussi le brut en chunks
					if bool(sum_cfg.get("store_raw", False)):
						for chunk in split_chunks(text, max_tokens=800):
							if store.upsert(chunk, {"source": url, "title": r.get("title"), "kind": "search_raw", "q": q}):
								learned += 1
				else:
					# fallback: stocker brut en chunks
					for chunk in split_chunks(text, max_tokens=800):
						if store.upsert(chunk, {"source": url, "title": r.get("title"), "kind": "search", "q": q}):
							learned += 1
							sources.append(url)
			else:
				# pas de résumé: stock brut en chunks
				for chunk in split_chunks(text, max_tokens=800):
					if store.upsert(chunk, {"source": url, "title": r.get("title"), "kind": "search", "q": q}):
						learned += 1
						sources.append(url)
	return {"learned_chunks": learned, "unique_sources": len(set(sources))}


def ingest_from_rss(cfg: dict, feeds: List[str], limit_per_feed: int, store: TinyRAG) -> Dict:
	learned = 0
	sources = []
	sec = (cfg.get("rag", {}) or {}).get("security", {})
	last_req: Dict[str, float] = {}
	domain_counts: Dict[str, int] = {}
	redact_patterns = (sec.get("redact_patterns") or [])
	sum_cfg = (cfg.get("rag", {}) or {}).get("summarize", {})
	for feed in feeds:
		try:
			d = feedparser.parse(feed)
		except Exception:
			continue
		for entry in d.entries[:limit_per_feed]:
			url = entry.get("link")
			if not url:
				continue
			domain = _get_domain(url)
			if domain_counts.get(domain, 0) >= int(sec.get("max_pages_per_domain", 5)):
				continue
			_rate_limit_wait(domain, sec, last_req)
			text, reason = fetch_page(url, sec)
			if not text:
				continue
			domain_counts[domain] = domain_counts.get(domain, 0) + 1
			text = _redact(text, redact_patterns)
			if (cfg.get("rag", {}).get("summarize", {}).get("enabled", False)):
				max_in = int(sum_cfg.get("max_input_chars", 8000))
				summary = _openai_summarize(cfg, text[:max_in])
				if summary:
					if store.upsert(summary, {"source": url, "title": entry.get("title"), "kind": "rss_summary", "feed": feed, "raw_len": len(text)}):
						learned += 1
						sources.append(url)
					if bool(sum_cfg.get("store_raw", False)):
						for chunk in split_chunks(text, max_tokens=800):
							if store.upsert(chunk, {"source": url, "title": entry.get("title"), "kind": "rss_raw", "feed": feed}):
								learned += 1
				else:
					for chunk in split_chunks(text, max_tokens=800):
						if store.upsert(chunk, {"source": url, "title": entry.get("title"), "kind": "rss", "feed": feed}):
							learned += 1
							sources.append(url)
			else:
				for chunk in split_chunks(text, max_tokens=800):
					if store.upsert(chunk, {"source": url, "title": entry.get("title"), "kind": "rss", "feed": feed}):
						learned += 1
						sources.append(url)
	return {"learned_chunks": learned, "unique_sources": len(set(sources))}


def main():
	cfg = load_cfg()
	rag_path = cfg.get("rag", {}).get("store_path", "data/rag.jsonl")
	store = TinyRAG(rag_path)

	summary = {"search": {}, "rss": {}}
	rag_cfg = cfg.get("rag", {})

	if rag_cfg.get("search", {}).get("enabled", True):
		queries = rag_cfg.get("search", {}).get("queries", [])
		max_results = int(rag_cfg.get("search", {}).get("max_results", 3))
		if queries:
			summary["search"] = ingest_from_search(cfg, queries, max_results, store)

	if rag_cfg.get("rss", {}).get("enabled", False):
		feeds = rag_cfg.get("rss", {}).get("feeds", [])
		limit_per_feed = int(rag_cfg.get("rss", {}).get("limit_per_feed", 3))
		if feeds:
			summary["rss"] = ingest_from_rss(cfg, feeds, limit_per_feed, store)

	os.makedirs(cfg["paths"]["logs_dir"], exist_ok=True)
	with open(os.path.join(cfg["paths"]["logs_dir"], "ingest_last.json"), "w", encoding="utf-8") as f:
		json.dump(summary, f, ensure_ascii=False, indent=2)
	print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
	main()
