#!/usr/bin/env python3
"""
enrich.py — Local search and discovery for ski resorts.

This script searches for information using Wikipedia and DuckDuckGo,
then uses your AI (OpenAI) to turn that text into structured data.
"""

import argparse
import sys
import time
from pathlib import Path
import requests
from bs4 import BeautifulSoup

try:
    from app import (
        DB_PATH, DEFAULT_MODEL, OPENAI_BASE_URL,
        classify_with_openai, generate_slug, init_db,
        parse_and_validate, save_to_db
    )
except ImportError as e:
    print(f"[ERROR] Import failed: {e}", file=sys.stderr)
    sys.exit(1)

# --- SETTINGS ---
SEARCH_DELAY_SEC = 2.0 
MAX_PAGES_TO_SCRAPE = 2 
HEADERS = {
    "User-Agent": "SkiResortDataBot/1.0 (test@example.com) - Educational project",
    "Accept-Language": "en-US,en;q=0.9",
}

def search_wikipedia(resort_name):
    """Looks up a resort on Wikipedia and returns the summary text."""
    api = "https://en.wikipedia.org/w/api.php"
    print(f"  [WEB] Searching Wikipedia: {resort_name}")
    try:
        # First, find the right page title
        resp = requests.get(api, params={
            "action": "query", "list": "search", "srsearch": f"{resort_name} ski resort",
            "srlimit": 3, "format": "json", "utf8": 1,
        }, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        results = resp.json().get("query", {}).get("search", [])
        if not results:
            return ""
        
        # Then, get the actual text content of that page
        resp = requests.get(api, params={
            "action": "query", "titles": results[0]["title"], "prop": "extracts",
            "explaintext": True, "exsectionformat": "plain", "exchars": 5000, "format": "json",
        }, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        return next(iter(resp.json().get("query", {}).get("pages", {}).values())).get("extract", "")
    except Exception as e:
        print(f"  [WARN] Wikipedia error: {e}")
        return ""

def search_duckduckgo(query):
    """Searches DuckDuckGo for additional websites about the resort."""
    print(f"  [SEARCH] Searching DuckDuckGo: {query}")
    try:
        resp = requests.post("https://lite.duckduckgo.com/lite/", data={"q": query}, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        # Find links that look like actual websites (not ads or internal links)
        urls = [a.get("href") for a in soup.find_all("a", class_="result-url") if a.get("href", "").startswith("http")]
        return [u for u in urls if not any(s in u for s in ["duckduckgo.com", "wikipedia.org"])][:MAX_PAGES_TO_SCRAPE]
    except Exception as e:
        print(f"  [WARN] DuckDuckGo error: {e}")
        return []

def scrape_page(url):
    """Downloads a website and extracts its text."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        # Remove navigation and styling to get clean text
        for tag in soup(["script", "style", "nav", "footer", "header"]): tag.decompose()
        text = "\n".join([l.strip() for l in soup.get_text("\n").splitlines() if l.strip()])
        return text[:4000]
    except Exception:
        return ""

def gather_text_for_resort(resort_name):
    """Combines Wikipedia and web search results into one big text block for the AI."""
    parts = []
    wiki_text = search_wikipedia(resort_name)
    if wiki_text: parts.append(f"=== Wikipedia ===\n{wiki_text}")

    # If Wikipedia didn't have much info, try a general web search
    if len(wiki_text) < 1000:
        print("  [INFO] Not enough data found, trying web search...")
        time.sleep(SEARCH_DELAY_SEC)
        for url in search_duckduckgo(f"{resort_name} ski resort trails altitude price"):
            print(f"  [INFO] Reading page: {url[:60]}...")
            if page_text := scrape_page(url): parts.append(f"=== {url} ===\n{page_text}")
            time.sleep(0.5)
            
    return "\n\n".join(parts)

def run_discover(resort_names, openai_url, model, db_path, dry_run):
    """Main loop that goes through the list of resorts and finds data for each."""
    print(f"\n[START] Starting search for {len(resort_names)} resorts...")
    conn = init_db(db_path)
    # Check what we already have in the database to avoid searching twice
    existing = {r[0] for r in conn.cursor().execute("SELECT slug FROM resort").fetchall()}
    conn.close()

    for name in resort_names:
        if not name.strip(): continue
        print(f"\n{'='*50}\n[PROCESS] Analyzing: {name}")
        
        # 1. Search for info
        if not (text := gather_text_for_resort(name)):
            continue

        # 2. Use AI to extract details
        print("  [AI] OpenAI is processing the text...")
        if not (resorts := parse_and_validate(classify_with_openai(text, model, openai_url))):
            continue

        # 3. Check for duplicates
        new = [r for r in resorts if generate_slug(r.name, r.country) not in existing]
        for r in new: existing.add(generate_slug(r.name, r.country))

        # 4. Save
        if new and not dry_run:
            save_to_db(new, source_url="discover:openai", db_path=db_path)
        
        time.sleep(SEARCH_DELAY_SEC)
    
    print("\n[FINISH] All tasks completed.")

def main():
    parser = argparse.ArgumentParser(description="Local ski resort discovery tool using OpenAI.")
    parser.add_argument("--db", default=DB_PATH, help="Path to database file")
    parser.add_argument("--dry-run", action="store_true", help="Don't save anything, just show output")
    parser.add_argument("--resorts", help='List of resort names separated by commas')
    parser.add_argument("--file", help="A text file with resort names (one per line)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="OpenAI model to use")
    parser.add_argument("--openai-url", default=OPENAI_BASE_URL)

    args = parser.parse_args()

    names = []
    if args.resorts:
        names = [r.strip() for r in args.resorts.split(",")]
    elif args.file:
        names = [l.strip() for l in Path(args.file).read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
    else:
        print("[ERROR] Please provide resort names using --resorts or --file", file=sys.stderr)
        sys.exit(1)

    run_discover(names, args.openai_url, args.model, args.db, args.dry_run)

if __name__ == "__main__":
    main()
