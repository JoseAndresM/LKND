"""
Collector: Music Ally Jobs  – https://musicallyjobs.com/jobs
Fuente: RSS (se actualiza varias veces al día)
"""
from __future__ import annotations
import feedparser, hashlib, datetime
from typing import List, Dict

RSS = "https://musicallyjobs.com/jobs/feed/"

def _hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]

def fetch() -> List[Dict]:
    feed = feedparser.parse(RSS)
    jobs: List[Dict] = []
    for e in feed.entries:
        posted = datetime.date(*e.published_parsed[:3]).isoformat()
        jobs.append({
            "job_id"      : f"musically-{_hash(e.link)}",
            "title"       : e.title,
            "company"     : e.get("author", ""),        # suele traer la empresa
            "country"     : "",                         # RSS no lo indica
            "city"        : "",
            "contract"    : "",
            "posted_date" : posted,
            "source"      : "Music Ally Jobs",
            "url"         : e.link,
            "description" : e.summary,
        })
    return jobs

if __name__ == "__main__":     # prueba rápida local
    import json, pprint
    pprint.pprint(fetch()[:3])
