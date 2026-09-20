"""Bounded NCBI searches and content-addressed, resumable HTTP snapshots."""
import hashlib
import json
import os
import time
from datetime import date, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

HELPERS = json.loads(Path(__file__).with_name("helpers.json").read_text())
BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"


def helper_query(helper):
    terms = "(" + " OR ".join('"' + term + '"[All Fields]' for term in HELPERS[helper]) + ")"
    # Target broad libraries before applying the experiment budget. Amplicon runs
    # otherwise dominate recent respiratory-virus submissions.
    libraries = '("RNA-Seq"[Strategy] OR ("WGS"[Strategy] AND "METAGENOMIC"[Source]))'
    if helper == "adenovirus":
        libraries = '("RNA-Seq"[Strategy] OR "WGS"[Strategy])'
    # Mature records are more likely to have archive-generated FASTQ mirrors.
    # The exact cutoff is recorded in parameters.json and reused on resume.
    cutoff = (date.today() - timedelta(days=90)).strftime("%Y/%m/%d")
    return terms + ' AND ' + libraries + ' AND "ILLUMINA"[Platform] NOT "PCR"[Selection] AND ("1900/01/01"[Publication Date] : "' + cutoff + '"[Publication Date])'


class Client:
    def __init__(self, directory, offline=False):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.offline = offline
        self.last_request = 0.0

    def get(self, base, params):
        public_url = base + "?" + urlencode(sorted(params.items()))
        key = hashlib.sha256(public_url.encode()).hexdigest()
        path = self.directory / (key + ".txt")
        meta_path = self.directory / (key + ".json")
        if path.exists() and meta_path.exists():
            data = path.read_bytes()
            meta = json.loads(meta_path.read_text())
            if hashlib.sha256(data).hexdigest() != meta["sha256"]:
                raise ValueError("Cached response checksum mismatch: " + key)
            return data.decode("utf-8")
        if self.offline:
            raise RuntimeError("Offline snapshot missing for " + public_url)
        private_params = dict(params)
        if base.startswith(BASE):
            private_params["tool"] = "satellite-discovery"
            if os.getenv("NCBI_EMAIL"):
                private_params["email"] = os.environ["NCBI_EMAIL"]
            if os.getenv("NCBI_API_KEY"):
                private_params["api_key"] = os.environ["NCBI_API_KEY"]
        request = Request(base + "?" + urlencode(private_params),
                          headers={"User-Agent": "satellite-discovery/0.1.0"})
        for attempt in range(4):
            time.sleep(max(0, 0.4 - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            try:
                with urlopen(request, timeout=45) as response:
                    data = response.read()
                decoded = data.decode("utf-8")
                if base.startswith(BASE):
                    if "<ERROR>" in decoded or '"error"' in decoded.lower():
                        raise ValueError("NCBI returned an API error; response not cached")
                part = path.with_suffix(".part")
                part.write_bytes(data)
                part.replace(path)
                meta_path.write_text(json.dumps({"url": public_url,
                    "retrieved_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "sha256": hashlib.sha256(data).hexdigest()}, indent=2))
                return decoded
            except HTTPError as exc:
                if exc.code not in (429, 500, 502, 503, 504):
                    raise RuntimeError(f"Public API returned HTTP {exc.code}") from None
                if attempt == 3:
                    raise RuntimeError(f"Public API HTTP {exc.code} after four attempts") from None
                delay = exc.headers.get("Retry-After", "")
                time.sleep(min(60, float(delay)) if delay.isdigit() else 2 ** attempt)
            except (URLError, TimeoutError):
                if attempt == 3:
                    raise RuntimeError("Public API connection failed after four attempts") from None
                time.sleep(2 ** attempt)

    def search(self, query, limit=20):
        ids = []
        count = 0
        translation = None
        for start in range(0, limit, 100):
            result = json.loads(self.get(BASE + "esearch.fcgi", {
                "db": "sra", "term": query, "retmode": "json", "sort": "relevance",
                "retstart": start, "retmax": min(100, limit - start)}))["esearchresult"]
            count = int(result["count"])
            translation = result.get("querytranslation")
            page = result["idlist"]
            ids.extend(page)
            if not page or len(ids) >= count:
                break
        return {"count": count, "ids": list(dict.fromkeys(ids)), "translation": translation}

    def fetch(self, ids):
        return self.get(BASE + "efetch.fcgi", {
            "db": "sra", "id": ",".join(ids), "retmode": "xml"})
