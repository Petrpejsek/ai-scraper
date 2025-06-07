from flask import Flask, render_template, request, jsonify, send_file
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time
import re
import threading
import json
import os
from datetime import datetime
import uuid

app = Flask(__name__)

# Globální store pro běžící úlohy
running_jobs = {}

class AIScraper:
    def __init__(self, job_id):
        self.job_id = job_id
        # Unikátní množina pro ukládání hlavních domén
        self.unique_domains = set()
        # AI související klíčová slova pro lepší detekci
        self.ai_keywords = ['ai', 'artificial', 'intelligence', 'tool', 'gpt', 'chat', 'bot', 'machine', 'learning', 'neural', 'openai', 'claude', 'gemini', 'copilot', 'assistant', 'generator', 'automation', 'smart', 'auto']
        # Seznam domén k ignorování (sociální sítě, běžné weby)
        self.ignore_domains = ['facebook.com', 'twitter.com', 'linkedin.com', 'youtube.com', 'google.com', 'github.com']
        
        # Nastavení pro ukládání výsledků
        self.results_dir = "results"
        if not os.path.exists(self.results_dir):
            os.makedirs(self.results_dir)
        self.results_file = os.path.join(self.results_dir, f"{job_id}_results.json")
        self.status_file = os.path.join(self.results_dir, f"{job_id}_status.json")
        
        # Načti existující výsledky do unique_domains pro prevenci duplicit
        self.load_existing_results()
        
        # Uložení počátečního stavu
        self.update_status("starting", "Inicializace scraperu...")
        
    def load_existing_results(self):
        """Načte existující výsledky pro prevenci duplicit"""
        if os.path.exists(self.results_file):
            try:
                with open(self.results_file, 'r', encoding='utf-8') as f:
                    existing_results = json.load(f)
                    for result in existing_results:
                        if result.get('url'):
                            self.unique_domains.add(result['url'])
                print(f"🔄 Načteno {len(self.unique_domains)} existujících URL pro prevenci duplicit")
            except Exception as e:
                print(f"⚠️  Nepodařilo se načíst existující výsledky: {e}")
                
    def update_status(self, status, message, found_count=0):
        """Aktualizuje stav úlohy"""
        status_data = {
            "status": status,  # starting, running, completed, error
            "message": message,
            "found_count": found_count,
            "timestamp": datetime.now().isoformat(),
            "job_id": self.job_id
        }
        
        with open(self.status_file, 'w', encoding='utf-8') as f:
            json.dump(status_data, f, ensure_ascii=False, indent=2)
        
        # Také aktualizuj globální store
        running_jobs[self.job_id] = status_data
        
    def save_batch(self, new_urls):
        """Uloží novou dávku URL do souboru s důslednou kontrolou duplicit"""
        if not new_urls:
            return
            
        # Načti existující výsledky
        all_results = []
        existing_urls = set()  # Množina pro rychlou kontrolu duplicit
        
        if os.path.exists(self.results_file):
            try:
                with open(self.results_file, 'r', encoding='utf-8') as f:
                    all_results = json.load(f)
                    # Vytvoř množinu existujících URL pro rychlou kontrolu
                    existing_urls = {r.get('url') for r in all_results if r.get('url')}
            except:
                all_results = []
                existing_urls = set()
        
        # Počítadlo skutečně nových URL
        actually_new = 0
        
        # Přidej pouze skutečně nové URL
        for url in new_urls:
            if url not in existing_urls:
                all_results.append({
                    "url": url,
                    "found_at": datetime.now().isoformat()
                })
                existing_urls.add(url)  # Přidej do množiny pro další kontroly
                actually_new += 1
                print(f"  ➕ Nové: {url}")
            else:
                print(f"  ⚠️  Duplikát ignorován: {url}")
        
        # Ulož zpět jen pokud jsou skutečně nová data
        if actually_new > 0:
            with open(self.results_file, 'w', encoding='utf-8') as f:
                json.dump(all_results, f, ensure_ascii=False, indent=2)
            print(f"✅ Uloženo {actually_new} nových URL. Celkem: {len(all_results)}")
        else:
            print(f"ℹ️  Žádné nové URL k uložení - všechny byly duplikáty")
        
    def is_ai_tool_domain(self, url):
        """Zjistí, zda je URL AI nástroj podle domény a kontextu"""
        try:
            domain = urlparse(url).netloc.lower()
            
            # Odstraň www. prefix
            if domain.startswith('www.'):
                domain = domain[4:]
            
            # Ignoruj známé ne-AI domény a původní stránku
            ignore_domains = self.ignore_domains + ['futurepedia.io', 'theresanaiforthat.com', 'futuretools.io', 'producthunt.com']
            for ignore in ignore_domains:
                if ignore in domain:
                    return False
            
            # Rozšířený seznam prioritních koncovek
            ai_extensions = ['.ai', '.io', '.app', '.tech', '.co']
            for ext in ai_extensions:
                if domain.endswith(ext):
                    return True
            
            # Pro .com, .org, .net domény - kontrola AI klíčových slov
            common_extensions = ['.com', '.org', '.net', '.dev', '.cc', '.me', '.ly']
            for ext in common_extensions:
                if domain.endswith(ext):
                    for keyword in self.ai_keywords:
                        if keyword in domain:
                            return True
            
            # Pokud má URL suggestivní path (např. obsahuje "tool", "ai")
            path = urlparse(url).path.lower()
            ai_path_keywords = ['tool', 'ai', 'gpt', 'chat', 'bot', 'generate', 'create']
            for keyword in ai_path_keywords:
                if keyword in path:
                    return True
            
            return False
            
        except Exception:
            return False
    
    def get_main_domain(self, url):
        """Vrátí hlavní doménu z URL"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            if domain.startswith('www.'):
                domain = domain[4:]
            return f"https://{domain}"
        except Exception:
            return None

    def extract_all_links_from_content(self, content, base_url):
        """Extrahuje všechny možné odkazy z obsahu stránky s důslednou kontrolou duplicit"""
        found_urls = []
        local_found_domains = set()  # Lokální kontrola duplicit pro tuto stránku
        
        # 1. Zkus najít URL v JSON datech
        json_patterns = [
            r'"websiteUrl":"(https?://[^"?]+)',
            r'"url":"(https?://[^"?]+)',
            r'"link":"(https?://[^"?]+)',
            r'"href":"(https?://[^"?]+)'
        ]
        
        for pattern in json_patterns:
            matches = re.findall(pattern, content)
            for url in matches:
                if self.is_ai_tool_domain(url):
                    main_domain = self.get_main_domain(url)
                    if main_domain and main_domain not in self.unique_domains and main_domain not in local_found_domains:
                        self.unique_domains.add(main_domain)
                        local_found_domains.add(main_domain)
                        found_urls.append(main_domain)
                        print(f"DEBUG: JSON AI nástroj: {main_domain}")
                    elif main_domain in self.unique_domains:
                        print(f"DEBUG: JSON duplikát ignorován: {main_domain}")
        
        # 2. Hledej URL v textu (např. api.domain.com v skriptech)
        url_pattern = r'https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:/[^\s"\'<>]*)?'
        text_urls = re.findall(url_pattern, content)
        
        for url in text_urls:
            if self.is_ai_tool_domain(url):
                main_domain = self.get_main_domain(url)
                if main_domain and main_domain not in self.unique_domains and main_domain not in local_found_domains:
                    self.unique_domains.add(main_domain)
                    local_found_domains.add(main_domain)
                    found_urls.append(main_domain)
                    print(f"DEBUG: TEXT AI nástroj: {main_domain}")
                elif main_domain in self.unique_domains:
                    print(f"DEBUG: TEXT duplikát ignorován: {main_domain}")
        
        print(f"DEBUG: Celkem nalezeno {len(found_urls)} NOVÝCH AI nástrojů z obsahu (ignorováno {len(local_found_domains) - len(found_urls)} duplikátů)")
        return found_urls

    def scrape_page(self, url, max_depth=2, current_depth=0, test_mode=False):
        """Projde stránku a najde AI nástroje s asynchronním ukládáním"""
        print(f"Scrapuji: {url} (hloubka: {current_depth})")
        
        try:
            # Aktualizuj stav
            self.update_status("running", f"Scrapuji: {url} (hloubka: {current_depth})", len(self.unique_domains))
            
            # Získá obsah stránky
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            content = response.text
            found_urls = []
            
            # Nejdříve zkusí extrahovat z obsahu stránky (JSON + text)
            content_urls = self.extract_all_links_from_content(content, url)
            found_urls.extend(content_urls)
            
            # ULOŽENÍ DÁVKY PRŮBĚŽNĚ (každých 10+ URL)
            if len(content_urls) > 0:
                self.save_batch(content_urls)
                self.update_status("running", f"Nalezeno {len(content_urls)} AI nástrojů na {url}", len(self.unique_domains))
            
            # Pokud v test módu najde dost URL z obsahu, zastav
            if test_mode and len(found_urls) >= 10:
                self.update_status("completed", f"TEST MÓD: Nalezeno {len(found_urls)} AI nástrojů", len(self.unique_domains))
                return found_urls[:10]
            
            # Pokud nenajde dost v JSON nebo není test mód, pokračuj běžným scrapingem
            soup = BeautifulSoup(content, 'html5lib')
            links = soup.find_all('a', href=True)
            subpages_to_visit = []
            
            # V test módu omezí zpracování na prvních 50 odkazů
            links_to_process = links[:50] if test_mode else links
            
            for link in links_to_process:
                href = link['href']
                
                # Převede relativní odkazy na absolutní
                full_url = urljoin(url, href)
                
                # Kontrola, zda je to AI nástroj
                if self.is_ai_tool_domain(full_url):
                    main_domain = self.get_main_domain(full_url)
                    if main_domain and main_domain not in self.unique_domains:
                        self.unique_domains.add(main_domain)
                        found_urls.append(main_domain)
                        print(f"Nalezen AI nástroj: {main_domain}")
                        
                        # PRŮBĚŽNÉ UKLÁDÁNÍ po každých 5 nálezech
                        if len(found_urls) % 5 == 0:
                            self.save_batch([main_domain])
                            
                        # V test módu zastav po nalezení 10 nástrojů
                        if test_mode and len(found_urls) >= 10:
                            self.update_status("completed", "TEST MÓD: Nalezeno 10 AI nástrojů", len(self.unique_domains))
                            self.save_batch(found_urls[-5:])  # ulož posledních 5
                            return found_urls[:10]
                
                # Shromáždí podstránky k prozkoumání (pouze ze stejné domény)
                elif current_depth < max_depth and not test_mode:  # V test módu neprocházej podstránky
                    if urlparse(full_url).netloc == urlparse(url).netloc:
                        if full_url not in subpages_to_visit and full_url != url:
                            subpages_to_visit.append(full_url)
            
            # Rekurzivně projde podstránky (pokud není test mód)
            if current_depth < max_depth and not test_mode:
                for subpage in subpages_to_visit[:10]:  # Omezí na 10 podstránek pro rychlost
                    time.sleep(1)  # Pause mezi požadavky
                    sub_results = self.scrape_page(subpage, max_depth, current_depth + 1, test_mode)
                    found_urls.extend(sub_results)
                    
                    # Ulož dávku po každé podstránce
                    if sub_results:
                        self.save_batch(sub_results)
            
            return found_urls
            
        except Exception as e:
            error_msg = f"Chyba při scrapování {url}: {str(e)}"
            print(error_msg)
            self.update_status("error", error_msg, len(self.unique_domains))
            return []

    def run_scraping_job(self, start_url, test_mode=False):
        """Spustí hlavní scraping úlohu"""
        try:
            self.update_status("running", f"Spouštím scraping {'v TEST módu' if test_mode else 'v PLNÉM módu'}...")
            
            results = self.scrape_page(start_url, max_depth=2, test_mode=test_mode)
            
            # Finální uložení
            if results:
                self.save_batch(results)
            
            final_count = len(self.unique_domains)
            self.update_status("completed", f"Scraping dokončen! Nalezeno {final_count} AI nástrojů.", final_count)
            
            return results
            
        except Exception as e:
            error_msg = f"Kritická chyba: {str(e)}"
            self.update_status("error", error_msg, len(self.unique_domains))
            return []

@app.route('/')
def index():
    """Hlavní stránka s formulářem"""
    return render_template('index.html')

@app.route('/scrape', methods=['POST'])
def scrape():
    """Spustí scraping v background threadu"""
    data = request.get_json()
    start_url = data.get('url')
    test_mode = data.get('test_mode', False)
    
    if not start_url:
        return jsonify({'error': 'URL není zadané'}), 400
    
    try:
        # Vytvoř unikátní ID pro úlohu
        job_id = str(uuid.uuid4())[:8]
        
        # Vytvoř nový scraper
        scraper = AIScraper(job_id)
        
        # Spusť scraping v background threadu
        def run_background_scraping():
            scraper.run_scraping_job(start_url, test_mode)
        
        thread = threading.Thread(target=run_background_scraping)
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True,
            'job_id': job_id,
            'message': f'Scraping spuštěn v pozadí! ID úlohy: {job_id}',
            'status_url': f'/status/{job_id}',
            'results_url': f'/results/{job_id}'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Chyba při spuštění: {str(e)}'
        }), 500

@app.route('/status/<job_id>')
def get_job_status(job_id):
    """Vrátí aktuální stav úlohy"""
    try:
        status_file = os.path.join("results", f"{job_id}_status.json")
        
        if not os.path.exists(status_file):
            return jsonify({
                'success': False,
                'message': 'Úloha nenalezena'
            }), 404
        
        with open(status_file, 'r', encoding='utf-8') as f:
            status_data = json.load(f)
        
        return jsonify({
            'success': True,
            'status': status_data['status'],
            'message': status_data['message'],
            'found_count': status_data.get('found_count', 0),
            'timestamp': status_data['timestamp'],
            'job_id': job_id
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Chyba při čtení stavu: {str(e)}'
        }), 500

@app.route('/results/<job_id>')
def get_job_results(job_id):
    """Vrátí výsledky úlohy po dávkách"""
    try:
        results_file = os.path.join("results", f"{job_id}_results.json")
        
        if not os.path.exists(results_file):
            return jsonify({
                'success': False,
                'message': 'Výsledky nenalezeny'
            }), 404
        
        with open(results_file, 'r', encoding='utf-8') as f:
            all_results = json.load(f)
        
        # Parametry pro stránkování
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        
        # Výpočet rozsahu
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        
        batch_results = all_results[start_idx:end_idx]
        has_more = end_idx < len(all_results)
        
        return jsonify({
            'success': True,
            'urls': [r['url'] for r in batch_results],
            'detailed_results': batch_results,
            'total_found': len(all_results),
            'page': page,
            'per_page': per_page,
            'has_more': has_more,
            'job_id': job_id
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Chyba při čtení výsledků: {str(e)}'
        }), 500

@app.route('/download/<job_id>')
def download_results(job_id):
    """Stáhne výsledky jako textový soubor"""
    try:
        results_file = os.path.join("results", f"{job_id}_results.json")
        
        if not os.path.exists(results_file):
            return jsonify({'error': 'Výsledky nenalezeny'}), 404
        
        with open(results_file, 'r', encoding='utf-8') as f:
            all_results = json.load(f)
        
        # Vytvoř textový soubor
        txt_content = "# AI Nástroje nalezené scraperem\n\n"
        for i, result in enumerate(all_results, 1):
            txt_content += f"{i}. {result['url']}\n"
        
        txt_file = os.path.join("results", f"{job_id}_urls.txt")
        with open(txt_file, 'w', encoding='utf-8') as f:
            f.write(txt_content)
        
        return send_file(txt_file, as_attachment=True, download_name=f"ai_tools_{job_id}.txt")
        
    except Exception as e:
        return jsonify({'error': f'Chyba při stahování: {str(e)}'}), 500

@app.route('/jobs')
def list_jobs():
    """Zobrazí seznam všech úloh"""
    try:
        if not os.path.exists("results"):
            return jsonify({'jobs': []})
        
        jobs = []
        for filename in os.listdir("results"):
            if filename.endswith("_status.json"):
                job_id = filename.replace("_status.json", "")
                
                with open(os.path.join("results", filename), 'r', encoding='utf-8') as f:
                    status_data = json.load(f)
                
                jobs.append({
                    'job_id': job_id,
                    'status': status_data['status'],
                    'message': status_data['message'],
                    'found_count': status_data.get('found_count', 0),
                    'timestamp': status_data['timestamp']
                })
        
        # Seřaď podle času (nejnovější první)
        jobs.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return jsonify({'jobs': jobs})
        
    except Exception as e:
        return jsonify({'error': f'Chyba při načítání úloh: {str(e)}'}), 500

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5001))
    print("Spouštím AI Scraper...")
    print(f"Otevřete http://localhost:{port} ve vašem prohlížeči")
    app.run(host='0.0.0.0', port=port, debug=False) 