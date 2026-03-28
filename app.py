"""
ski_aggregator.py — Ski resort data extractor using local AI.

This script does four things:
  1. Downloads a webpage from a URL.
  2. Sends the text to a local AI (Ollama) to find structured data.
  3. Checks if the data is correct using Pydantic.
  4. Saves the results to a local database (SQLite) and avoids duplicates.

To use:
  python app.py https://example.com/ski-article
"""

import argparse
import json
import sys
import re
import time
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, List

import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field, ValidationError

# --- SETTINGS & DATA MODELS ---
# These models define exactly what information we want to collect.

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "mistral:7b"  # A balanced model for standard home computers
DB_PATH = "resorts.db"

class ResortAltitude(BaseModel):
    """Mountain height information in meters."""
    base_m: Optional[int] = Field(None, ge=0, le=5000)          # Bottom of the resort
    peak_m: Optional[int] = Field(None, ge=0, le=6000)          # Highest point
    vertical_drop_m: Optional[int] = Field(None, ge=0, le=4000) # Total skiable height

class ResortTrails(BaseModel):
    """Details about the ski runs."""
    total_count: Optional[int] = Field(None, ge=0)
    total_km: Optional[float] = Field(None, ge=0)
    beginner_pct: Optional[float] = Field(None, ge=0, le=100)
    intermediate_pct: Optional[float] = Field(None, ge=0, le=100)
    advanced_pct: Optional[float] = Field(None, ge=0, le=100)
    off_piste: Optional[bool] = None

class ResortPrices(BaseModel):
    """Cost information in Euros."""
    day_pass_adult_eur: Optional[float] = Field(None, ge=0, le=500)
    season_pass_eur: Optional[float] = Field(None, ge=0)

class ResortInfrastructure(BaseModel):
    """Facilities and convenience."""
    ski_in_ski_out: Optional[bool] = None
    distance_to_airport_km: Optional[float] = Field(None, ge=0)
    family_friendly: Optional[bool] = None

class ResortModel(BaseModel):
    """The complete data profile for a single resort."""
    name: str
    country: str
    region: Optional[str] = None
    website: Optional[str] = None
    altitude: Optional[ResortAltitude] = Field(default_factory=ResortAltitude)
    trails: Optional[ResortTrails] = Field(default_factory=ResortTrails)
    prices: Optional[ResortPrices] = Field(default_factory=ResortPrices)
    infrastructure: Optional[ResortInfrastructure] = Field(default_factory=ResortInfrastructure)
    summary: Optional[str] = None

# This is a template we show the AI so it knows how to format its answer
SCHEMA_DESCRIPTION = """
{
  "resorts": [
    {
      "name": "string (required)",
      "country": "string (required)",
      "region": "string",
      "altitude": {"base_m": "number", "peak_m": "number", "vertical_drop_m": "number"},
      "trails": {"total_km": "number", "beginner_pct": "number", "intermediate_pct": "number", "advanced_pct": "number", "off_piste": "boolean"},
      "prices": {"day_pass_adult_eur": "number"},
      "infrastructure": {"ski_in_ski_out": "boolean", "distance_to_airport_km": "number", "family_friendly": "boolean"},
      "summary": "short summary"
    }
  ]
}
"""

SYSTEM_PROMPT = """You are a data extraction AI. Extract ski resort details from text into strict JSON.
RULES:
1. ONLY return JSON. No explanations.
2. Root key must be "resorts" containing a list.
3. Use null for missing values. Convert prices to EUR and distances to metric.
4. Extract ALL resorts mentioned."""

# --- DATABASE LOGIC ---
# This part handles saving the data so we don't lose it when the program closes.

def init_db(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Creates the database file and the table if they are missing."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS resort (
            slug                  TEXT PRIMARY KEY,  -- Unique ID (e.g., france_chamonix)
            name                  TEXT,
            country               TEXT,
            region                TEXT,
            base_m                INTEGER,
            peak_m                INTEGER,
            total_km              REAL,
            beginner_pct          REAL,
            day_pass_adult_eur    REAL,
            ski_in_ski_out        BOOLEAN,
            distance_to_airport_km REAL,
            summary               TEXT,
            source_url            TEXT,
            updated_at            TIMESTAMP
        )
    """)
    conn.commit()
    return conn

def generate_slug(name: str, country: str) -> str:
    """Creates a simple ID from the name and country to identify the resort."""
    clean_name = re.sub(r'[^a-z0-9]', '', name.lower())
    clean_country = re.sub(r'[^a-z0-9]', '', country.lower())
    return f"{clean_country}_{clean_name}"

def save_to_db(resorts: List[ResortModel], source_url: str, db_path: str = DB_PATH) -> None:
    """Writes the resort information to the database file."""
    if not resorts:
        print("[!] No resorts found to save.")
        return

    conn = init_db(db_path)
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()

    saved_count = 0
    for r in resorts:
        slug = generate_slug(r.name, r.country)
        
        # Pull data out of the nested models for the database
        base_m     = r.altitude.base_m if r.altitude else None
        peak_m     = r.altitude.peak_m if r.altitude else None
        total_km   = r.trails.total_km if r.trails else None
        beg_pct    = r.trails.beginner_pct if r.trails else None
        price      = r.prices.day_pass_adult_eur if r.prices else None
        ski_in     = r.infrastructure.ski_in_ski_out if r.infrastructure else None
        airport_km = r.infrastructure.distance_to_airport_km if r.infrastructure else None

        # This command saves the data. If the resort already exists, it updates the info.
        cursor.execute("""
            INSERT INTO resort (
                slug, name, country, region, base_m, peak_m, total_km,
                beginner_pct, day_pass_adult_eur, ski_in_ski_out,
                distance_to_airport_km, summary, source_url, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(slug) DO UPDATE SET
                base_m                 = COALESCE(EXCLUDED.base_m, resort.base_m),
                peak_m                 = COALESCE(EXCLUDED.peak_m, resort.peak_m),
                total_km               = COALESCE(EXCLUDED.total_km, resort.total_km),
                day_pass_adult_eur     = COALESCE(EXCLUDED.day_pass_adult_eur, resort.day_pass_adult_eur),
                updated_at             = EXCLUDED.updated_at
        """, (
            slug, r.name, r.country, r.region, base_m, peak_m, total_km,
            beg_pct, price, ski_in, airport_km, r.summary, source_url, now
        ))
        saved_count += 1

    conn.commit()
    conn.close()
    print(f"[OK] Successfully saved/updated {saved_count} resorts in the database.")

# --- WEB SCRAPER & AI CONNECTOR ---
# This part gets the text from the internet and sends it to the AI.

def fetch_article(url: str) -> str:
    """Downloads a webpage and strips away the menus and ads, leaving just the text."""
    print(f"[INFO] Downloading: {url}")
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        # Remove parts of the site we don't need
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        text = soup.get_text(separator="\n")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines)
    except Exception as e:
        print(f"[ERROR] Download failed: {e}", file=sys.stderr)
        sys.exit(1)

def classify_with_ollama(text: str, model: str, ollama_url: str) -> str:
    """Sends the website text to your local AI to find resort details."""
    # We shorten the text if it's too long so the computer doesn't get stuck
    max_chars = 8000
    if len(text) > max_chars:
        text = text[:max_chars].rsplit('.', 1)[0] + "."
        print(f"[INFO] Text shortened to {len(text)} characters for better performance.")

    prompt = f"Extract resorts into JSON.\nSCHEMA:\n{SCHEMA_DESCRIPTION}\n\nTEXT:\n{text}"
    payload = {
        "model": model, "system": SYSTEM_PROMPT, "prompt": prompt, "stream": False,
        "options": {"temperature": 0.0, "num_predict": 1000}
    }

    print(f"[INFO] Sending to Ollama ({model})... This uses your CPU.")
    start = time.time()
    try:
        resp = requests.post(f"{ollama_url}/api/generate", json=payload, timeout=900)
        resp.raise_for_status()
        print(f"[OK] AI finished in {time.time() - start:.1f}s.")
        return resp.json().get("response", "")
    except Exception as e:
        print(f"[ERROR] Ollama connection error: {e}", file=sys.stderr)
        sys.exit(1)

def parse_and_validate(raw_llm_response: str) -> List[ResortModel]:
    """Cleans the AI's response and checks if the data follows our rules."""
    # Remove extra formatting characters the AI might include
    cleaned = re.sub(r"```json|```", "", raw_llm_response).strip()
    
    try:
        data = json.loads(cleaned)
        resort_list = data.get("resorts", [])
        validated = []
        for item in resort_list:
            try:
                # This ensures the data (like height) isn't an impossible number
                validated.append(ResortModel(**item))
            except ValidationError as ve:
                print(f"[SKIP] Invalid data for {item.get('name', 'Unknown')}: {ve}")
        return validated
    except json.JSONDecodeError:
        print("[ERROR] AI did not return valid JSON. Try again or check the model.")
        return []

# --- MAIN EXECUTION ---

def main():
    parser = argparse.ArgumentParser(description="Extract ski resort info from a URL using local AI.")
    parser.add_argument("url", help="URL of the article or website to scan")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="The AI model name in Ollama")
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL, help="The address of your Ollama server")
    args = parser.parse_args()

    # Step 1: Get the text
    page_text = fetch_article(args.url)
    
    # Step 2: Let the AI find the data
    raw_response = classify_with_ollama(page_text, args.model, args.ollama_url)
    
    # Step 3: Check and clean the data
    resorts = parse_and_validate(raw_response)
    
    # Step 4: Save to the database
    save_to_db(resorts, source_url=args.url)

if __name__ == "__main__":
    main()