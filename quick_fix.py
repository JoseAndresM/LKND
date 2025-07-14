# quick_fix.py - Versión simplificada para testear
import os
import json
import requests
from datetime import datetime
from bs4 import BeautifulSoup
import hashlib

def send_telegram_message(token, chat_id, message):
    """Envía mensaje a Telegram"""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'Markdown'
    }
    try:
        response = requests.post(url, json=data)
        print(f"Telegram response: {response.status_code}")
    except Exception as e:
        print(f"Error enviando a Telegram: {e}")

def scrape_indeed():
    """Scraper básico para Indeed"""
    print("Buscando en Indeed...")
    url = "https://www.indeed.com/q-music-industry-jobs.html"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        jobs = []
        job_cards = soup.select('.job_seen_beacon')[:5]  # Solo 5 para prueba
        
        for card in job_cards:
            try:
                title = card.select_one('h2.jobTitle span[title]')
                company = card.select_one('[data-testid="company-name"]')
                location = card.select_one('[data-testid="job-location"]')
                
                if title:
                    job = {
                        'title': title.text.strip(),
                        'company': company.text.strip() if company else 'N/A',
                        'location': location.text.strip() if location else 'Remote',
                        'source': 'Indeed'
                    }
                    jobs.append(job)
            except:
                continue
        
        return jobs
    except Exception as e:
        print(f"Error en Indeed: {e}")
        return []

def main():
    """Función principal simplificada"""
    print("🚀 Iniciando bot simplificado...")
    
    # Obtener variables
    token = os.environ.get('TG_TOKEN')
    chat_id = os.environ.get('TG_CHAT_ID')
    
    if not token or not chat_id:
        print("❌ Error: No se encontraron las variables TG_TOKEN o TG_CHAT_ID")
        return 1
    
    print(f"✅ Variables cargadas")
    print(f"Chat ID: {chat_id}")
    
    # Crear directorio data si no existe
    os.makedirs('data', exist_ok=True)
    
    # Cargar base de datos
    db_file = 'data/simple_jobs.json'
    if os.path.exists(db_file):
        with open(db_file, 'r') as f:
            db = json.load(f)
    else:
        db = {'jobs': {}, 'last_run': None}
    
    print(f"📊 Base de datos cargada. Jobs actuales: {len(db['jobs'])}")
    
    # Buscar trabajos
    jobs = scrape_indeed()
    print(f"🔍 Encontrados {len(jobs)} trabajos")
    
    # Identificar nuevos
    new_jobs = []
    for job in jobs:
        job_id = hashlib.md5(f"{job['title']}{job['company']}".encode()).hexdigest()[:8]
        if job_id not in db['jobs']:
            db['jobs'][job_id] = job
            new_jobs.append(job)
    
    print(f"✨ Nuevos trabajos: {len(new_jobs)}")
    
    # Enviar notificación si hay nuevos
    if new_jobs:
        message = f"🎵 *Nuevos trabajos musicales encontrados!*\n\n"
        for job in new_jobs[:3]:
            message += f"📍 *{job['title']}*\n"
            message += f"🏢 {job['company']}\n"
            message += f"📌 {job['location']}\n\n"
        
        if len(new_jobs) > 3:
            message += f"_...y {len(new_jobs) - 3} más_"
        
        send_telegram_message(token, chat_id, message)
    else:
        message = "✅ Bot funcionando correctamente\n"
        message += f"📊 No hay trabajos nuevos\n"
        message += f"💾 Total en DB: {len(db['jobs'])} trabajos"
        send_telegram_message(token, chat_id, message)
    
    # Guardar base de datos
    db['last_run'] = datetime.now().isoformat()
    with open(db_file, 'w') as f:
        json.dump(db, f, indent=2)
    
    print("✅ Proceso completado")
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())
