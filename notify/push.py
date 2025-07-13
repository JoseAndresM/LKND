# notify/push.py  – versión “debug” sin librerías extra
import os, json, pathlib, textwrap, requests

TG_TOKEN   = os.getenv("TG_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")
LATEST     = pathlib.Path("jobs_latest.json")

def snippet(txt, n=200):
    return (txt[:n].rstrip() + "…") if len(txt) > n else txt

def send(msg: str) -> None:
    url  = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = {
        "chat_id": TG_CHAT_ID,
        "text": msg,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    r = requests.post(url, data=data, timeout=10)
    # 🔎 imprime SIEMPRE la respuesta JSON de Telegram
    print("Telegram raw reply:", r.text)
    if not r.json().get("ok"):
        raise RuntimeError("Telegram devolvió error ↑")

def main() -> None:
    if not (TG_TOKEN and TG_CHAT_ID):
        print("⚠️  Falta TG_TOKEN o TG_CHAT_ID")
        return
    if not LATEST.exists():
        print("⚠️  jobs_latest.json no existe")
        return

    for job in json.loads(LATEST.read_text()):
        msg = textwrap.dedent(f"""
            🎵 <b>{job['title']}</b>
            {job['company']} · {job['city']}
            {snippet(job['description'])}

            👉 <a href="{job['url']}">Ver oferta</a>
        """).strip()
        send(msg)

if __name__ == "__main__":
    main()

