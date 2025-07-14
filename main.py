# main.py - Sistema unificado de búsqueda de trabajos musicales
import os
import json
import time
import requests
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set
from dataclasses import dataclass, asdict
from bs4 import BeautifulSoup
import schedule
from telegram import Bot, Update
from telegram.ext import Updater, CommandHandler, CallbackContext
import openai
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import re

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class Job:
    """Estructura de datos para trabajos"""
    id: str
    title: str
    company: str
    location: str
    url: str
    description: str = ""
    salary: Optional[str] = None
    job_type: Optional[str] = None
    posted_date: Optional[str] = None
    source: str = ""
    found_date: str = ""
    tags: List[str] = None
    
    def __post_init__(self):
        if not self.found_date:
            self.found_date = datetime.now().isoformat()
        if self.tags is None:
            self.tags = []

class MusicJobsBot:
    """Bot principal para búsqueda de trabajos musicales"""
    
    def __init__(self):
        # Cargar configuración desde variables de entorno
        self.telegram_token = os.environ.get('TG_TOKEN')
        self.chat_id = os.environ.get('TG_CHAT_ID')
        self.openai_key = os.environ.get('OPENAI_API_KEY')
        
        # Inicializar componentes
        self.bot = Bot(token=self.telegram_token) if self.telegram_token else None
        self.db_file = 'data/jobs_database.json'
        self.config_file = 'data/config.json'
        self.stats_file = 'data/statistics.json'
        
        # Configurar OpenAI si está disponible
        if self.openai_key:
            openai.api_key = self.openai_key
        
        # Sites de trabajo especializados en música - MOVER ESTO ANTES
        self.job_sites = [
            {
                'name': 'Music Business Worldwide',
                'url': 'https://jobs.musicbusinessworldwide.com/',
                'scraper': self.scrape_mbw,
                'selectors': {
                    'container': '.job-listing',
                    'title': '.job-title',
                    'company': '.company',
                    'location': '.location',
                    'link': 'a'
                }
            },
            {
                'name': 'Entertainment Careers',
                'url': 'https://www.entertainmentcareers.net/jobs/music/',
                'scraper': self.scrape_entertainment_careers,
                'selectors': {
                    'container': '.job-item',
                    'title': 'h3',
                    'company': '.company-name',
                    'location': '.location',
                    'link': 'a'
                }
            },
            {
                'name': 'Indeed Music',
                'url': 'https://www.indeed.com/q-music-industry-jobs.html',
                'scraper': self.scrape_indeed,
                'selectors': {
                    'container': '.job_seen_beacon',
                    'title': 'h2.jobTitle span[title]',
                    'company': '[data-testid="company-name"]',
                    'location': '[data-testid="job-location"]',
                    'link': 'h2.jobTitle a'
                }
            },
            {
                'name': 'Music Jobs UK',
                'url': 'https://uk.music-jobs.com/',
                'scraper': self.scrape_generic,
                'selectors': {
                    'container': '.job-ad',
                    'title': '.job-title',
                    'company': '.employer',
                    'location': '.location',
                    'link': 'a'
                }
            },
            {
                'name': 'LinkedIn Music Jobs',
                'url': 'https://www.linkedin.com/jobs/search/?keywords=music%20industry',
                'scraper': self.scrape_linkedin,
                'requires_auth': True
            }
        ]
        
        # Categorías de trabajos musicales
        self.job_categories = {
            'Production': ['producer', 'engineer', 'mixing', 'mastering', 'studio', 'recording'],
            'Performance': ['musician', 'artist', 'performer', 'dj', 'singer', 'band'],
            'Business': ['manager', 'agent', 'marketing', 'promotion', 'label', 'a&r'],
            'Technical': ['developer', 'programmer', 'tech', 'software', 'streaming'],
            'Creative': ['composer', 'songwriter', 'arranger', 'sound design'],
            'Education': ['teacher', 'instructor', 'professor', 'tutor'],
            'Live Events': ['tour', 'venue', 'festival', 'concert', 'production'],
            'Media': ['journalist', 'writer', 'editor', 'content', 'social media']
        }
        
        # Cargar datos - AHORA SÍ, DESPUÉS DE DEFINIR job_sites
        self.jobs_db = self.load_database()
        self.config = self.load_config()
        self.stats = self.load_stats()
    
    def load_database(self) -> Dict:
        """Carga la base de datos de trabajos"""
        os.makedirs('data', exist_ok=True)
        if os.path.exists(self.db_file):
            try:
                with open(self.db_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                logger.error("Error cargando base de datos, creando nueva")
        
        return {
            'jobs': {},
            'last_updated': None,
            'total_jobs_found': 0,
            'sources_stats': {}
        }
    
    def load_config(self) -> Dict:
        """Carga configuración del bot"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        
        # Configuración por defecto
        return {
            'max_jobs_per_site': 50,
            'notification_batch_size': 10,
            'scraping_delay': 1,  # segundos entre requests
            'user_filters': {
                'keywords': [],
                'excluded_keywords': [],
                'locations': [],
                'min_salary': None,
                'job_types': []
            },
            'active_sites': ['Music Business Worldwide', 'Entertainment Careers', 'Indeed Music', 'Music Jobs UK']
        }
    
    def load_stats(self) -> Dict:
        """Carga estadísticas"""
        if os.path.exists(self.stats_file):
            try:
                with open(self.stats_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        
        return {
            'total_searches': 0,
            'total_jobs_found': 0,
            'jobs_by_category': {},
            'jobs_by_location': {},
            'jobs_by_company': {},
            'daily_stats': {}
        }
    
    def save_all_data(self):
        """Guarda todos los datos"""
        # Guardar base de datos
        self.jobs_db['last_updated'] = datetime.now().isoformat()
        with open(self.db_file, 'w', encoding='utf-8') as f:
            json.dump(self.jobs_db, f, indent=2, ensure_ascii=False)
        
        # Guardar configuración
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent=2)
        
        # Guardar estadísticas
        with open(self.stats_file, 'w') as f:
            json.dump(self.stats, f, indent=2)
    
    def generate_job_id(self, title: str, company: str, url: str) -> str:
        """Genera ID único para evitar duplicados"""
        content = f"{title.lower()}{company.lower()}{url}"
        return hashlib.md5(content.encode()).hexdigest()[:16]
    
    def extract_salary(self, text: str) -> Optional[str]:
        """Extrae información de salario del texto"""
        salary_patterns = [
            r'\$[\d,]+\s*-\s*\$[\d,]+(?:\s*(?:per|/)\s*(?:year|yr|annual))?',
            r'\$[\d,]+(?:\s*(?:per|/)\s*(?:year|yr|annual))',
            r'[\d,]+\s*-\s*[\d,]+\s*(?:EUR|GBP|USD)',
            r'\$[\d,]+(?:\s*(?:per|/)\s*(?:hour|hr))',
            r'£[\d,]+\s*-\s*£[\d,]+',
        ]
        
        for pattern in salary_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0)
        return None
    
    def categorize_job(self, job: Job) -> List[str]:
        """Categoriza un trabajo según su título y descripción"""
        text = f"{job.title} {job.description}".lower()
        categories = []
        
        for category, keywords in self.job_categories.items():
            if any(keyword in text for keyword in keywords):
                categories.append(category)
        
        return categories or ['Other']
    
    def scrape_generic(self, site_config: Dict) -> List[Job]:
        """Scraper genérico para sitios simples"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(site_config['url'], headers=headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            jobs = []
            
            selectors = site_config['selectors']
            job_containers = soup.select(selectors['container'])[:self.config['max_jobs_per_site']]
            
            for container in job_containers:
                try:
                    title_elem = container.select_one(selectors['title'])
                    company_elem = container.select_one(selectors['company'])
                    location_elem = container.select_one(selectors['location'])
                    link_elem = container.select_one(selectors['link'])
                    
                    if not title_elem or not link_elem:
                        continue
                    
                    # Construir URL completa
                    job_url = link_elem.get('href', '')
                    if job_url and not job_url.startswith('http'):
                        from urllib.parse import urljoin
                        job_url = urljoin(site_config['url'], job_url)
                    
                    job = Job(
                        id="",  # Se generará después
                        title=title_elem.text.strip(),
                        company=company_elem.text.strip() if company_elem else 'Unknown',
                        location=location_elem.text.strip() if location_elem else 'Not specified',
                        url=job_url,
                        source=site_config['name']
                    )
                    
                    # Generar ID único
                    job.id = self.generate_job_id(job.title, job.company, job.url)
                    
                    # Intentar extraer más información
                    desc_elem = container.select_one('.description, .summary')
                    if desc_elem:
                        job.description = desc_elem.text.strip()[:500]
                        job.salary = self.extract_salary(job.description)
                    
                    # Categorizar
                    job.tags = self.categorize_job(job)
                    
                    jobs.append(job)
                    
                except Exception as e:
                    logger.error(f"Error parseando trabajo: {e}")
                    continue
            
            logger.info(f"Encontrados {len(jobs)} trabajos en {site_config['name']}")
            return jobs
            
        except Exception as e:
            logger.error(f"Error scraping {site_config['name']}: {e}")
            return []
    
    def scrape_mbw(self, site_config: Dict) -> List[Job]:
        """Scraper específico para Music Business Worldwide"""
        # Usa el scraper genérico con ajustes específicos si es necesario
        return self.scrape_generic(site_config)
    
    def scrape_entertainment_careers(self, site_config: Dict) -> List[Job]:
        """Scraper específico para Entertainment Careers"""
        return self.scrape_generic(site_config)
    
    def scrape_indeed(self, site_config: Dict) -> List[Job]:
        """Scraper específico para Indeed"""
        # Indeed requiere manejo especial
        jobs = self.scrape_generic(site_config)
        
        # Post-procesamiento específico de Indeed
        for job in jobs:
            # Indeed a veces incluye información extra
            if 'Remote' in job.location:
                job.job_type = 'Remote'
            
        return jobs
    
    def scrape_linkedin(self, site_config: Dict) -> List[Job]:
        """LinkedIn requiere autenticación - placeholder"""
        logger.info("LinkedIn requiere autenticación - omitiendo por ahora")
        return []
    
    def scrape_all_sites(self) -> List[Job]:
        """Scraping paralelo de todos los sitios activos"""
        all_jobs = []
        
        # Filtrar solo sitios activos
        active_sites = [
            site for site in self.job_sites 
            if site['name'] in self.config['active_sites'] and not site.get('requires_auth')
        ]
        
        # Scraping paralelo con ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_site = {
                executor.submit(site['scraper'], site): site 
                for site in active_sites
            }
            
            for future in as_completed(future_to_site):
                site = future_to_site[future]
                try:
                    jobs = future.result()
                    all_jobs.extend(jobs)
                    
                    # Actualizar estadísticas por fuente
                    self.jobs_db['sources_stats'][site['name']] = {
                        'last_scraped': datetime.now().isoformat(),
                        'jobs_found': len(jobs)
                    }
                    
                except Exception as e:
                    logger.error(f"Error en {site['name']}: {e}")
                
                # Delay entre sitios
                time.sleep(self.config['scraping_delay'])
        
        return all_jobs
    
    def filter_jobs(self, jobs: List[Job]) -> List[Job]:
        """Aplica filtros de usuario a los trabajos"""
        filtered_jobs = []
        filters = self.config['user_filters']
        
        for job in jobs:
            # Texto completo para búsqueda
            job_text = f"{job.title} {job.company} {job.description}".lower()
            
            # Filtrar por palabras clave (debe contener al menos una)
            if filters['keywords']:
                if not any(kw.lower() in job_text for kw in filters['keywords']):
                    continue
            
            # Excluir por palabras clave
            if filters['excluded_keywords']:
                if any(kw.lower() in job_text for kw in filters['excluded_keywords']):
                    continue
            
            # Filtrar por ubicación
            if filters['locations']:
                location_match = any(
                    loc.lower() in job.location.lower() 
                    for loc in filters['locations']
                )
                if not location_match and 'remote' not in filters['locations']:
                    continue
            
            # Filtrar por tipo de trabajo
            if filters['job_types']:
                type_match = any(
                    jt.lower() in job.job_type.lower() if job.job_type else False
                    for jt in filters['job_types']
                )
                if not type_match:
                    continue
            
            filtered_jobs.append(job)
        
        return filtered_jobs
    
    def find_new_jobs(self, scraped_jobs: List[Job]) -> List[Job]:
        """Identifica trabajos nuevos que no están en la base de datos"""
        new_jobs = []
        
        for job in scraped_jobs:
            if job.id not in self.jobs_db['jobs']:
                # Agregar a la base de datos
                self.jobs_db['jobs'][job.id] = asdict(job)
                new_jobs.append(job)
                
                # Actualizar estadísticas
                self.update_statistics(job)
        
        return new_jobs
    
    def update_statistics(self, job: Job):
        """Actualiza estadísticas con nuevo trabajo"""
        # Total de trabajos
        self.stats['total_jobs_found'] += 1
        
        # Por categoría
        for category in job.tags:
            self.stats['jobs_by_category'][category] = \
                self.stats['jobs_by_category'].get(category, 0) + 1
        
        # Por ubicación
        location = job.location.split(',')[0].strip()  # Primera parte de la ubicación
        self.stats['jobs_by_location'][location] = \
            self.stats['jobs_by_location'].get(location, 0) + 1
        
        # Por empresa
        self.stats['jobs_by_company'][job.company] = \
            self.stats['jobs_by_company'].get(job.company, 0) + 1
        
        # Estadísticas diarias
        today = datetime.now().strftime('%Y-%m-%d')
        if today not in self.stats['daily_stats']:
            self.stats['daily_stats'][today] = {
                'jobs_found': 0,
                'sources': {}
            }
        
        self.stats['daily_stats'][today]['jobs_found'] += 1
        self.stats['daily_stats'][today]['sources'][job.source] = \
            self.stats['daily_stats'][today]['sources'].get(job.source, 0) + 1
    
    def format_telegram_message(self, jobs: List[Job]) -> str:
        """Formatea mensaje para Telegram"""
        if not jobs:
            return "No se encontraron nuevos trabajos en esta búsqueda."
        
        message = f"🎵 *Nuevos trabajos en la industria musical* 🎵\n"
        message += f"_Encontrados {len(jobs)} nuevos trabajos_\n\n"
        
        # Agrupar por categoría
        jobs_by_category = {}
        for job in jobs[:self.config['notification_batch_size']]:
            for category in job.tags:
                if category not in jobs_by_category:
                    jobs_by_category[category] = []
                jobs_by_category[category].append(job)
        
        # Mostrar trabajos por categoría
        for category, category_jobs in jobs_by_category.items():
            message += f"*{category}*\n"
            
            for job in category_jobs[:3]:  # Máximo 3 por categoría
                message += f"\n📍 *{job.title}*\n"
                message += f"🏢 {job.company}\n"
                message += f"📌 {job.location}\n"
                
                if job.salary:
                    message += f"💰 {job.salary}\n"
                
                if job.job_type:
                    message += f"🏷️ {job.job_type}\n"
                
                message += f"🔗 [Ver más]({job.url})\n"
                message += f"_Fuente: {job.source}_\n"
            
            if len(category_jobs) > 3:
                message += f"\n_...y {len(category_jobs) - 3} más en {category}_\n"
            
            message += "\n"
        
        if len(jobs) > self.config['notification_batch_size']:
            message += f"\n📊 *Total: {len(jobs)} nuevos trabajos encontrados*"
        
        # Añadir resumen
        message += "\n\n📈 *Resumen rápido:*\n"
        location_summary = {}
        for job in jobs:
            loc = job.location.split(',')[0].strip()
            location_summary[loc] = location_summary.get(loc, 0) + 1
        
        top_locations = sorted(location_summary.items(), key=lambda x: x[1], reverse=True)[:3]
        for loc, count in top_locations:
            message += f"• {loc}: {count} trabajos\n"
        
        return message
    
    def send_telegram_notification(self, message: str):
        """Envía notificación a Telegram"""
        if not self.telegram_token or not self.chat_id:
            logger.warning("Telegram no configurado")
            return
        
        try:
            # Dividir mensaje si es muy largo
            max_length = 4000
            if len(message) > max_length:
                # Enviar en partes
                parts = [message[i:i+max_length] for i in range(0, len(message), max_length)]
                for part in parts:
                    self.bot.send_message(
                        chat_id=self.chat_id,
                        text=part,
                        parse_mode='Markdown',
                        disable_web_page_preview=True
                    )
                    time.sleep(1)  # Evitar rate limiting
            else:
                self.bot.send_message(
                    chat_id=self.chat_id,
                    text=message,
                    parse_mode='Markdown',
                    disable_web_page_preview=True
                )
            
            logger.info("Notificación enviada exitosamente")
            
        except Exception as e:
            logger.error(f"Error enviando notificación: {e}")
    
    def generate_ai_insights(self, jobs: List[Job]) -> Optional[str]:
        """Genera insights usando OpenAI"""
        if not self.openai_key or not jobs:
            return None
        
        try:
            # Preparar datos para el análisis
            job_summaries = []
            for job in jobs[:50]:  # Limitar para no exceder tokens
                summary = f"- {job.title} at {job.company} in {job.location}"
                if job.tags:
                    summary += f" (Categories: {', '.join(job.tags)})"
                job_summaries.append(summary)
            
            # Estadísticas para el prompt
            categories_count = {}
            locations_count = {}
            companies_count = {}
            
            for job in jobs:
                for cat in job.tags:
                    categories_count[cat] = categories_count.get(cat, 0) + 1
                
                loc = job.location.split(',')[0].strip()
                locations_count[loc] = locations_count.get(loc, 0) + 1
                
                companies_count[job.company] = companies_count.get(job.company, 0) + 1
            
            prompt = f"""Analiza estos {len(jobs)} trabajos en la industria musical:

{chr(10).join(job_summaries[:30])}

Estadísticas:
- Categorías principales: {', '.join([f"{k}: {v}" for k, v in sorted(categories_count.items(), key=lambda x: x[1], reverse=True)[:5]])}
- Ubicaciones top: {', '.join([f"{k}: {v}" for k, v in sorted(locations_count.items(), key=lambda x: x[1], reverse=True)[:5]])}
- Empresas más activas: {', '.join([f"{k}: {v}" for k, v in sorted(companies_count.items(), key=lambda x: x[1], reverse=True)[:5]])}

Genera insights profesionales sobre:
1. Tendencias emergentes en roles y habilidades demandadas
2. Análisis geográfico del mercado laboral musical
3. Tipos de empresas y sectores con más oportunidades
4. Recomendaciones específicas para profesionales de la música
5. Predicciones a corto plazo basadas en los datos

Formato: Análisis profesional conciso en español, con bullet points claros y accionables."""

            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system", 
                        "content": "Eres un experto analista del mercado laboral en la industria musical con 20 años de experiencia."
                    },
                    {"role": "user", "content": prompt}
                ],
                max_tokens=800,
                temperature=0.7
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Error generando insights con AI: {e}")
            return None
    
    def generate_weekly_report(self) -> str:
        """Genera reporte semanal completo"""
        week_ago = datetime.now() - timedelta(days=7)
        
        # Filtrar trabajos de la última semana
        weekly_jobs = []
        for job_id, job_data in self.jobs_db['jobs'].items():
            job_date = datetime.fromisoformat(job_data['found_date'])
            if job_date >= week_ago:
                weekly_jobs.append(Job(**job_data))
        
        if not weekly_jobs:
            return "No se encontraron trabajos nuevos esta semana."
        
        # Generar insights con IA si está disponible
        ai_insights = self.generate_ai_insights(weekly_jobs)
        
        # Construir reporte
        report = f"📊 *REPORTE SEMANAL - Industria Musical* 📊\n"
        report += f"_Período: {week_ago.strftime('%d/%m')} - {datetime.now().strftime('%d/%m/%Y')}_\n\n"
        
        report += f"📈 *RESUMEN EJECUTIVO*\n"
        report += f"• Total de nuevas oportunidades: {len(weekly_jobs)}\n"
        report += f"• Promedio diario: {len(weekly_jobs) / 7:.1f} trabajos\n\n"
        
        # Top categorías
        categories = {}
        for job in weekly_jobs:
            for cat in job.tags:
                categories[cat] = categories.get(cat, 0) + 1
        
        report += f"🎯 *CATEGORÍAS MÁS DEMANDADAS*\n"
        for cat, count in sorted(categories.items(), key=lambda x: x[1], reverse=True)[:5]:
            percentage = (count / len(weekly_jobs)) * 100
            report += f"• {cat}: {count} trabajos ({percentage:.1f}%)\n"
        
        # Top ubicaciones
        locations = {}
        for job in weekly_jobs:
            loc = job.location.split(',')[0].strip()
            locations[loc] = locations.get(loc, 0) + 1
        
        report += f"\n🌍 *UBICACIONES PRINCIPALES*\n"
        for loc, count in sorted(locations.items(), key=lambda x: x[1], reverse=True)[:5]:
            report += f"• {loc}: {count} ofertas\n"
        
        # Empresas más activas
        companies = {}
        for job in weekly_jobs:
            companies[job.company] = companies.get(job.company, 0) + 1
        
        report += f"\n🏢 *EMPRESAS MÁS ACTIVAS*\n"
        for company, count in sorted(companies.items(), key=lambda x: x[1], reverse=True)[:5]:
            report += f"• {company}: {count} posiciones\n"
        
        # Insights de IA
        if ai_insights:
            report += f"\n🤖 *ANÁLISIS INTELIGENTE*\n"
            report += ai_insights
        
        # Recomendaciones
        report += f"\n\n💡 *RECOMENDACIONES DE LA SEMANA*\n"
        
        # Basadas en datos
        if 'Remote' in locations and locations['Remote'] > 5:
            report += "• ✅ Alta demanda de trabajo remoto - considera ampliar tu búsqueda geográfica\n"
        
        if 'Production' in categories and categories['Production'] > len(weekly_jobs) * 0.2:
            report += "• 🎚️ Fuerte demanda en producción musical - destaca tu experiencia técnica\n"
        
        if len(companies) > 20:
            report += "• 🌟 Mercado diversificado - explora empresas emergentes además de las tradicionales\n"
        
        # Tendencias de salario
        salaries_found = sum(1 for job in weekly_jobs if job.salary)
        if salaries_found > len(weekly_jobs) * 0.3:
            report += f"• 💰 {salaries_found} trabajos con salario público - negocia con información\n"
        
        report += f"\n📅 *Próximo reporte: {(datetime.now() + timedelta(days=7)).strftime('%d/%m/%Y')}*"
        
        return report
    
    def run_scheduled_search(self):
        """Ejecuta búsqueda programada"""
        logger.info(f"🔍 Iniciando búsqueda programada - {datetime.now()}")
        
        # Actualizar estadísticas
        self.stats['total_searches'] += 1
        
        try:
            # Scraping de todos los sitios
            all_jobs = self.scrape_all_sites()
            logger.info(f"Total trabajos encontrados: {len(all_jobs)}")
            
            # Aplicar filtros
            filtered_jobs = self.filter_jobs(all_jobs)
            logger.info(f"Trabajos después de filtros: {len(filtered_jobs)}")
            
            # Identificar nuevos
            new_jobs = self.find_new_jobs(filtered_jobs)
            logger.info(f"Trabajos nuevos: {len(new_jobs)}")
            
            # Notificar si hay nuevos
            if new_jobs:
                message = self.format_telegram_message(new_jobs)
                self.send_telegram_notification(message)
            
            # Guardar todo
            self.save_all_data()
            
            return len(new_jobs)
            
        except Exception as e:
            logger.error(f"Error en búsqueda programada: {e}")
            return 0
    
    def setup_telegram_commands(self):
        """Configura comandos de Telegram"""
        if not self.telegram_token:
            return
        
        updater = Updater(self.telegram_token, use_context=True)
        dp = updater.dispatcher
        
        # Comandos disponibles
        dp.add_handler(CommandHandler("start", self.cmd_start))
        dp.add_handler(CommandHandler("help", self.cmd_help))
        dp.add_handler(CommandHandler("stats", self.cmd_stats))
        dp.add_handler(CommandHandler("search", self.cmd_search))
        dp.add_handler(CommandHandler("filters", self.cmd_filters))
        dp.add_handler(CommandHandler("sites", self.cmd_sites))
        dp.add_handler(CommandHandler("report", self.cmd_report))
        dp.add_handler(CommandHandler("export", self.cmd_export))
        
        return updater
    
    def cmd_start(self, update: Update, context: CallbackContext):
        """Comando /start"""
        welcome_message = """
🎵 *Bienvenido al Bot de Trabajos Musicales* 🎵

Este bot busca automáticamente oportunidades laborales en la industria musical y te notifica cuando encuentra nuevas ofertas.

*Comandos disponibles:*
/help - Ver todos los comandos
/stats - Ver estadísticas
/search - Buscar ahora
/filters - Configurar filtros
/sites - Ver/modificar sitios activos
/report - Generar reporte
/export - Exportar datos

*Características:*
• Búsqueda automática cada 2 horas
• Filtros personalizables
• Análisis semanal con IA
• Múltiples fuentes de trabajo
• Categorización inteligente

_Bot creado con ❤️ para la comunidad musical_
"""
        update.message.reply_text(welcome_message, parse_mode='Markdown')
    
    def cmd_help(self, update: Update, context: CallbackContext):
        """Comando /help"""
        help_text = """
📚 *AYUDA COMPLETA*

*Comandos básicos:*
• /search - Ejecuta búsqueda manual inmediata
• /stats - Muestra estadísticas generales
• /report - Genera reporte semanal

*Configuración:*
• /filters - Configura tus filtros personalizados
• /sites - Activa/desactiva sitios de búsqueda

*Filtros disponibles:*
• /filters keywords [palabras] - Buscar estas palabras
• /filters exclude [palabras] - Excluir estas palabras
• /filters location [ciudad] - Filtrar por ubicación
• /filters type [remote/onsite] - Tipo de trabajo
• /filters clear - Limpiar todos los filtros

*Exportar datos:*
• /export csv - Exportar a CSV
• /export json - Exportar a JSON

*Ejemplos:*
`/filters keywords producer engineer`
`/filters location London Remote`
`/filters exclude intern junior`
"""
        update.message.reply_text(help_text, parse_mode='Markdown')
    
    def cmd_stats(self, update: Update, context: CallbackContext):
        """Comando /stats"""
        total_jobs = len(self.jobs_db['jobs'])
        
        # Estadísticas de los últimos 7 días
        week_ago = datetime.now() - timedelta(days=7)
        recent_jobs = sum(
            1 for job in self.jobs_db['jobs'].values()
            if datetime.fromisoformat(job['found_date']) >= week_ago
        )
        
        # Top categorías
        all_categories = {}
        for job in self.jobs_db['jobs'].values():
            for cat in job.get('tags', []):
                all_categories[cat] = all_categories.get(cat, 0) + 1
        
        top_categories = sorted(all_categories.items(), key=lambda x: x[1], reverse=True)[:5]
        
        stats_message = f"""
📊 *ESTADÍSTICAS GENERALES*

*Base de datos:*
• Total trabajos almacenados: {total_jobs}
• Nuevos últimos 7 días: {recent_jobs}
• Total búsquedas realizadas: {self.stats['total_searches']}

*Categorías principales:*
{chr(10).join([f"• {cat}: {count} trabajos" for cat, count in top_categories])}

*Fuentes activas:* {len([s for s in self.config['active_sites']])}

*Última actualización:* {self.jobs_db.get('last_updated', 'Nunca')}
"""
        update.message.reply_text(stats_message, parse_mode='Markdown')
    
    def cmd_search(self, update: Update, context: CallbackContext):
        """Comando /search - búsqueda manual"""
        update.message.reply_text("🔍 Iniciando búsqueda manual...")
        
        # Ejecutar búsqueda
        new_jobs = self.run_scheduled_search()
        
        if new_jobs > 0:
            update.message.reply_text(f"✅ Búsqueda completada. {new_jobs} nuevos trabajos encontrados!")
        else:
            update.message.reply_text("✅ Búsqueda completada. No se encontraron trabajos nuevos.")
    
    def cmd_filters(self, update: Update, context: CallbackContext):
        """Comando /filters - gestión de filtros"""
        if len(context.args) == 0:
            # Mostrar filtros actuales
            filters = self.config['user_filters']
            current = f"""
🔧 *FILTROS ACTUALES*

*Palabras clave:* {', '.join(filters['keywords']) if filters['keywords'] else 'Ninguna'}
*Palabras excluidas:* {', '.join(filters['excluded_keywords']) if filters['excluded_keywords'] else 'Ninguna'}
*Ubicaciones:* {', '.join(filters['locations']) if filters['locations'] else 'Todas'}
*Tipos de trabajo:* {', '.join(filters['job_types']) if filters['job_types'] else 'Todos'}

Usa `/filters [tipo] [valores]` para modificar
"""
            update.message.reply_text(current, parse_mode='Markdown')
            return
        
        filter_type = context.args[0].lower()
        values = context.args[1:] if len(context.args) > 1 else []
        
        if filter_type == 'keywords':
            self.config['user_filters']['keywords'] = values
            update.message.reply_text(f"✅ Palabras clave actualizadas: {', '.join(values)}")
        
        elif filter_type == 'exclude':
            self.config['user_filters']['excluded_keywords'] = values
            update.message.reply_text(f"✅ Palabras excluidas actualizadas: {', '.join(values)}")
        
        elif filter_type == 'location':
            self.config['user_filters']['locations'] = values
            update.message.reply_text(f"✅ Ubicaciones actualizadas: {', '.join(values)}")
        
        elif filter_type == 'type':
            self.config['user_filters']['job_types'] = values
            update.message.reply_text(f"✅ Tipos de trabajo actualizados: {', '.join(values)}")
        
        elif filter_type == 'clear':
            self.config['user_filters'] = {
                'keywords': [],
                'excluded_keywords': [],
                'locations': [],
                'job_types': [],
                'min_salary': None
            }
            update.message.reply_text("✅ Todos los filtros han sido limpiados")
        
        else:
            update.message.reply_text("❌ Tipo de filtro no válido. Usa: keywords, exclude, location, type, o clear")
            return
        
        # Guardar configuración
        self.save_all_data()
    
    def cmd_sites(self, update: Update, context: CallbackContext):
        """Comando /sites - gestión de sitios activos"""
        if len(context.args) == 0:
            # Mostrar sitios actuales
            sites_status = "🌐 *SITIOS DE BÚSQUEDA*\n\n"
            
            for site in self.job_sites:
                if site.get('requires_auth'):
                    status = "🔒 Requiere autenticación"
                elif site['name'] in self.config['active_sites']:
                    status = "✅ Activo"
                else:
                    status = "❌ Inactivo"
                
                sites_status += f"• {site['name']}: {status}\n"
            
            sites_status += "\nUsa `/sites [enable/disable] [nombre]` para modificar"
            update.message.reply_text(sites_status, parse_mode='Markdown')
            return
        
        action = context.args[0].lower()
        site_name = ' '.join(context.args[1:]) if len(context.args) > 1 else ''
        
        # Buscar sitio
        site_names = [s['name'] for s in self.job_sites if not s.get('requires_auth')]
        
        if site_name not in site_names:
            update.message.reply_text(f"❌ Sitio no encontrado. Disponibles: {', '.join(site_names)}")
            return
        
        if action == 'enable':
            if site_name not in self.config['active_sites']:
                self.config['active_sites'].append(site_name)
                update.message.reply_text(f"✅ {site_name} activado")
            else:
                update.message.reply_text(f"ℹ️ {site_name} ya estaba activo")
        
        elif action == 'disable':
            if site_name in self.config['active_sites']:
                self.config['active_sites'].remove(site_name)
                update.message.reply_text(f"✅ {site_name} desactivado")
            else:
                update.message.reply_text(f"ℹ️ {site_name} ya estaba inactivo")
        
        else:
            update.message.reply_text("❌ Acción no válida. Usa: enable o disable")
            return
        
        # Guardar configuración
        self.save_all_data()
    
    def cmd_report(self, update: Update, context: CallbackContext):
        """Comando /report - genera reporte semanal"""
        update.message.reply_text("📊 Generando reporte semanal...")
        
        report = self.generate_weekly_report()
        
        # Dividir si es muy largo
        if len(report) > 4000:
            parts = [report[i:i+4000] for i in range(0, len(report), 4000)]
            for part in parts:
                update.message.reply_text(part, parse_mode='Markdown')
                time.sleep(1)
        else:
            update.message.reply_text(report, parse_mode='Markdown')
    
    def cmd_export(self, update: Update, context: CallbackContext):
        """Comando /export - exportar datos"""
        format_type = context.args[0].lower() if context.args else 'csv'
        
        if format_type == 'csv':
            # Generar CSV
            import csv
            import io
            
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Headers
            writer.writerow(['ID', 'Title', 'Company', 'Location', 'URL', 'Category', 'Source', 'Date Found'])
            
            # Data
            for job_id, job in self.jobs_db['jobs'].items():
                writer.writerow([
                    job_id,
                    job.get('title', ''),
                    job.get('company', ''),
                    job.get('location', ''),
                    job.get('url', ''),
                    ', '.join(job.get('tags', [])),
                    job.get('source', ''),
                    job.get('found_date', '')
                ])
            
            # Enviar archivo
            output.seek(0)
            update.message.reply_document(
                document=io.BytesIO(output.getvalue().encode()),
                filename=f'music_jobs_{datetime.now().strftime("%Y%m%d")}.csv',
                caption="📊 Exportación CSV de todos los trabajos"
            )
        
        elif format_type == 'json':
            # Enviar JSON
            update.message.reply_document(
                document=io.BytesIO(json.dumps(self.jobs_db, indent=2).encode()),
                filename=f'music_jobs_{datetime.now().strftime("%Y%m%d")}.json',
                caption="📊 Exportación JSON de la base de datos completa"
            )
        
        else:
            update.message.reply_text("❌ Formato no válido. Usa: /export csv o /export json")
    
    def run_bot(self):
        """Ejecuta el bot con todas sus funcionalidades"""
        logger.info("🚀 Iniciando Music Jobs Bot...")
        
        # Configurar comandos de Telegram si está disponible
        telegram_updater = None
        if self.telegram_token:
            telegram_updater = self.setup_telegram_commands()
            
            # Iniciar en thread separado
            import threading
            telegram_thread = threading.Thread(target=telegram_updater.start_polling)
            telegram_thread.daemon = True
            telegram_thread.start()
            logger.info("✅ Bot de Telegram iniciado")
        
        # Programar tareas
        # Búsqueda cada 2 horas
        schedule.every(2).hours.do(self.run_scheduled_search)
        
        # Reporte semanal los domingos a las 10 AM
        schedule.every().sunday.at("10:00").do(lambda: self.send_telegram_notification(self.generate_weekly_report()))
        
        # Ejecutar primera búsqueda
        logger.info("Ejecutando primera búsqueda...")
        self.run_scheduled_search()
        
        # Loop principal
        logger.info("Bot operativo. Esperando tareas programadas...")
        
        try:
            while True:
                schedule.run_pending()
                time.sleep(60)  # Verificar cada minuto
                
        except KeyboardInterrupt:
            logger.info("Deteniendo bot...")
            if telegram_updater:
                telegram_updater.stop()
            self.save_all_data()
            logger.info("✅ Bot detenido correctamente")


# Para GitHub Actions
def github_actions_mode():
    """Modo especial para GitHub Actions - una sola ejecución"""
    bot = MusicJobsBot()
    
    # Ejecutar búsqueda
    new_jobs = bot.run_scheduled_search()
    
    # Si es domingo, generar reporte semanal
    if datetime.now().weekday() == 6:  # Domingo
        report = bot.generate_weekly_report()
        bot.send_telegram_notification(report)
    
    print(f"✅ Ejecución completada. {new_jobs} nuevos trabajos encontrados.")
    
    # Retornar código de salida
    return 0 if new_jobs >= 0 else 1


if __name__ == "__main__":
    import sys
    
    # Detectar si estamos en GitHub Actions
    if os.environ.get('GITHUB_ACTIONS') == 'true':
        sys.exit(github_actions_mode())
    else:
        # Modo normal - ejecutar continuamente
        bot = MusicJobsBot()
        bot.run_bot()
