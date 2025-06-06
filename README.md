# 🤖 AI Nástroje Scraper

Jednoduchý web scraper pro hledání a extrakci URL adres AI nástrojů ze srovnávacích stránek.

## 🚀 Jak spustit aplikaci

### 1. Nainstalování potřebných balíčků
```bash
pip install -r requirements.txt
```

### 2. Spuštění aplikace
```bash
python3 app.py
```

### 3. Otevření v prohlížeči
Otevřete prohlížeč a jděte na: **http://localhost:5000**

## 📖 Jak používat

1. **Zadejte URL**: Do formuláře vložte adresu stránky se srovnáním AI nástrojů
2. **Spusťte scraping**: Klikněte na "Spustit Scraping"
3. **Čekejte na výsledky**: Aplikace projde stránku a najde všechny AI nástroje
4. **Kopírujte URL**: Výsledky se zobrazí po dávkách 50 URL, které můžete kopírovat

## 🔍 Co aplikace dělá

- **Prohledává stránky**: Projde hlavní stránku + všechny podstránky
- **Filtruje AI nástroje**: Hledá domény končící na `.ai`, `.io` a `.com` s AI klíčovými slovy
- **Odstraňuje duplikáty**: Každá doména se zobrazí jen jednou
- **Vytváří dávky**: Výsledky rozdělí do skupin po 50 URL pro snadné kopírování

## ⚙️ Technické detaily

- **Python Flask** - webový server
- **BeautifulSoup** - parsování HTML stránek
- **Requests** - stahování obsahu stránek
- **Jednoduchý HTML/CSS/JavaScript** - frontend

## 🛠️ Co se děje na pozadí

1. Aplikace stáhne obsah zadané stránky
2. Najde všechny odkazy na stránce
3. Pro každý odkaz kontroluje, zda je to AI nástroj (podle domény a klíčových slov)
4. Rekurzivně prochází i podstránky (max 2 úrovně hloubky)
5. Ukládá jen hlavní domény (bez podstránek) a odstraňuje duplikáty
6. Vrací výsledky po dávkách 50 URL

## 📝 Poznámky

- Scraping může trvat několik minut v závislosti na velikosti stránky
- Aplikace respektuje server a dělá pauzy mezi požadavky
- Ignoruje běžné weby jako Facebook, Google, YouTube apod. 