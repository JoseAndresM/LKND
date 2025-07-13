import json, pathlib
from collect.doors_open import fetch as fetch_doors

COLLECTORS = [fetch_doors, fetch_musically,]

if __name__ == "__main__":
    all_jobs = []
    for fetcher in COLLECTORS:
        try:
            all_jobs.extend(fetcher())
        except Exception as e:
            print(f"[WARN] Collector {fetcher.__name__} failed → {e}")

    path = pathlib.Path("raw_jobs.json")
    path.write_text(json.dumps(all_jobs, ensure_ascii=False, indent=2))
    print(f"✅  Collected {len(all_jobs)} jobs → {path.resolve()}")
