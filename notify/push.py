def send(msg):
    url  = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = {
        "chat_id": TG_CHATID,
        "text": msg,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    r = requests.post(url, data=data, timeout=10)

    # ⬇️  imprime siempre la respuesta
    print("Telegram raw reply:", r.text)

    j = r.json()
    if not j.get("ok"):
        raise RuntimeError(f"Telegram error: {j}")
