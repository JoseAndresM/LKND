"""
Envía por Telegram las vacantes recién insertadas (jobs_latest.json)
Requiere variables de entorno:
  TG_TOKEN   → token de BotFather
  TG_CHAT_ID → id númerico o @usuario/@canal donde enviar
"""
import os, json, pathlib, textwrap, sys
from telegram import Bot

LATEST = pathlib.Path("jobs_latest.json")

def snippet(txt: str, n=200) -> str:
    return (txt[: n].rstrip() + "…") if len(txt) > n else txt

def main() -> None:
    if not LATEST.exists():
        print("No hay jobs_latest.json → nada que enviar")
        return

    tg_token   = os.getenv("TG_TOKEN")
    tg_chat_id = os.getenv("TG_CHAT_ID")
    if not tg_token or not tg_chat_id:
        print("❌ Falta TG_TOKEN o TG_CHAT_ID")
        sys.exit(1)

    jobs = json.loads(LATEST.read_text())
    if not jobs:
        print("📭 0 ofertas nuevas → silencioso")
        return

    bot = Bot(tg_token)
    for j in jobs:
        text = textwrap.dedent(f"""
            🎵 <b>{j['title']}</b>
            {j['company']} · {j['city']}
            {snippet(j['description'])}

            👉 <a href="{j['url']}">Ver oferta completa</a>
        """).strip()
        bot.send_message(
            chat_id=tg_chat_id,
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    print(f"🚀 Enviados {len(jobs)} avisos a Telegram")

if __name__ == "__main__":
    main()
