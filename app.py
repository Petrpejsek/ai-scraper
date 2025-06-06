from flask import Flask, render_template, request, jsonify
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time
import re

app = Flask(__name__)

class AIScraper:
    def __init__(self):
        # Unikátní množina pro ukládání hlavních domén
        self.unique_domains = set()
        # AI související klíčová slova pro lepší detekci
        self.ai_keywords = ['ai', 'artificial', 'intelligence', 'tool', 'gpt', 'chat', 'bot', 'machine', 'learning', 'neural', 'openai', 'claude', 'gemini', 'copilot', 'assistant', 'generator', 'automation', 'smart', 'auto']
        # Seznam domén k ignorování (sociální sítě, běžné weby)
        self.ignore_domains = ['facebook.com', 'twitter.com', 'linkedin.com', 'youtube.com', 'google.com', 'github.com']
        
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
        """Extrahuje všechny možné odkazy z obsahu stránky"""
        found_urls = []
        
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
                    if main_domain and main_domain not in self.unique_domains:
                        self.unique_domains.add(main_domain)
                        found_urls.append(main_domain)
                        print(f"DEBUG: JSON AI nástroj: {main_domain}")
        
        # 2. Hledej URL v textu (např. api.domain.com v skriptech)
        url_pattern = r'https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:/[^\s"\'<>]*)?'
        text_urls = re.findall(url_pattern, content)
        
        for url in text_urls:
            if self.is_ai_tool_domain(url):
                main_domain = self.get_main_domain(url)
                if main_domain and main_domain not in self.unique_domains:
                    self.unique_domains.add(main_domain)
                    found_urls.append(main_domain)
                    print(f"DEBUG: TEXT AI nástroj: {main_domain}")
        
        print(f"DEBUG: Celkem nalezeno {len(found_urls)} AI nástrojů z obsahu")
        return found_urls

    def scrape_page(self, url, max_depth=2, current_depth=0, test_mode=False):
        """Projde stránku a najde AI nástroje"""
        print(f"Scrapuji: {url} (hloubka: {current_depth})")
        
        try:
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
            
            # Pokud v test módu najde dost URL z obsahu, zastav
            if test_mode and len(found_urls) >= 10:
                print(f"TEST MÓD: Nalezeno {len(found_urls)} AI nástrojů z obsahu, ukončuji...")
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
                        
                        # V test módu zastav po nalezení 10 nástrojů
                        if test_mode and len(found_urls) >= 10:
                            print("TEST MÓD: Nalezeno 10 AI nástrojů, ukončuji...")
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
            
            return found_urls
            
        except Exception as e:
            print(f"Chyba při scrapování {url}: {str(e)}")
            return []

# Globální instance scraperu
scraper = AIScraper()

@app.route('/')
def index():
    """Hlavní stránka s formulářem"""
    return render_template('index.html')

@app.route('/scrape', methods=['POST'])
def scrape():
    """Spustí scraping a vrátí první dávku URL"""
    global scraper
    
    data = request.get_json()
    start_url = data.get('url')
    test_mode = data.get('test_mode', False)
    
    if not start_url:
        return jsonify({'error': 'URL není zadané'}), 400
    
    try:
        # Restartuje scraper pro nový běh
        scraper = AIScraper()
        
        # Spustí scraping
        print(f"Spouštím scraping v {'TEST' if test_mode else 'PLNÉM'} módu...")
        found_urls = scraper.scrape_page(start_url, max_depth=2, test_mode=test_mode)
        
        # Vrátí první dávku (50 URL, ale v test módu bude méně)
        batch = found_urls[:50]
        remaining = len(found_urls) - 50
        
        return jsonify({
            'success': True,
            'urls': batch,
            'total_found': len(found_urls),
            'remaining': max(0, remaining),
            'has_more': remaining > 0,
            'test_mode': test_mode
        })
        
    except Exception as e:
        return jsonify({'error': f'Chyba při scrapování: {str(e)}'}), 500

@app.route('/get_next_batch', methods=['POST'])
def get_next_batch():
    """Vrátí další dávku URL"""
    global scraper
    
    data = request.get_json()
    offset = data.get('offset', 0)
    
    all_urls = list(scraper.unique_domains)
    batch = all_urls[offset:offset + 50]
    remaining = len(all_urls) - offset - 50
    
    return jsonify({
        'urls': batch,
        'remaining': max(0, remaining),
        'has_more': remaining > 0
    })

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5001))
    print("Spouštím AI Scraper...")
    print(f"Otevřete http://localhost:{port} ve vašem prohlížeči")
    app.run(host='0.0.0.0', port=port, debug=False) 