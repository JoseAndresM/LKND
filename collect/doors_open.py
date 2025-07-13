"""Scraper para Doors Open – vacantes de la industria musical"""
from __future__ import annotations
import requests, hashlib, datetime, re
from bs4 import BeautifulSoup
from typing import List, Dict

BASE_URL = "https://doorsopen.co"
JOB_LIST  = f"{BASE_URL}/jobs?query=&remote=&industry=music"
HEADERS   = {"User-Agent": "Mozilla/5.0 (MusicJobRadar/0.1)"}


def _hash(title: str, company: str, city: str) -> str:
    key = f"{title}|{company}|{city}".lower().encode()
    return hashlib.sha256(key).hexdigest()[:16]


def _get_description(url: str) -> str:
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        node = soup.select_one("div.job-description")
        return node.get_text("\n", strip=True) if node else ""
    except Exception:
        return ""


def fetch() -> List[Dict]:
    r = requests.get(JOB_LIST, headers=HEADERS, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    jobs: List[Dict] = []
    for card in soup.select("div.job-item"):
        title   = card.select_one("h3.job-title").get_text(strip=True)
        company = card.select_one("div.company-name").get_text(strip=True)
        city    = card.select_one("div.location").get_text(strip=True)
        url     = BASE_URL + card.select_one("a")["href"]

        # «Posted 3 days ago» → fecha ISO
        posted_raw  = card.select_one("div.posted-date").get_text()
        m = re.search(r"(\d+)\s+day", posted_raw)
        posted_date = (datetime.date.today() -
                       datetime.timedelta(days=int(m.group(1))) if m
                       else datetime.date.today()).isoformat()

        jobs.append({
            "job_id"      : f"door-{_hash(title, company, city)}",
            "title"       : title,
            "company"     : company,
            "country"     : "",          # se derivará luego
            "city"        : city,
            "contract"    : "",          # idem
            "posted_date" : posted_date,
            "source"      : "Doors Open",
            "url"         : url,
            "description" : _get_description(url),
        })
    return jobs


if __name__ == "__main__":
    from pprint import pprint
    pprint(fetch()[:2])
