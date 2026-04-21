"""
app.py — Ski resort data extractor using an OpenAI-compatible API.

This script does four things:
  1. Downloads a webpage from a URL.
  2. Sends the text to an AI via API to find structured data.
  3. Checks if the data is correct using Pydantic.
  4. Saves the results to a local database (SQLite) and avoids duplicates.

To use:
  python ski_aggregator.py https://example.com/ski-article
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
import os

import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field, ValidationError

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = "https://kurim.ithope.eu/v1"
DEFAULT_MODEL = "gemma3:27b"  
DB_PATH = "resorts.db"


def log_msg(stage: str, message: str) -> None:
    """Prints a formatted log message with a timestamp and forces immediate output."""
    current_time = datetime.now().strftime("%H:%M:%S")
    # flush=True is crucial for streaming logs to the web interface in real-time
    print(f"[{current_time}] [{stage.upper()}] {message}", flush=True)


class ResortAltitude(BaseModel):
    base_m: Optional[int] = Field(None, ge=0, le=5000)         
    peak_m: Optional[int] = Field(None, ge=0, le=6000)         
    vertical_drop_m: Optional[int] = Field(None, ge=0, le=4000)

class ResortTrails(BaseModel):
    total_count: Optional[int] = Field(None, ge=0)
    total_km: Optional[float] = Field(None, ge=0)
    beginner_pct: Optional[float] = Field(None, ge=0, le=100)
    intermediate_pct: Optional[float] = Field(None, ge=0, le=100)
    advanced_pct: Optional[float] = Field(None, ge=0, le=100)
    off_piste: Optional[bool] = None

class ResortPrices(BaseModel):
    day_pass_adult_eur: Optional[float] = Field(None, ge=0, le=500)
    season_pass_eur: Optional[float] = Field(None, ge=0)

class ResortInfrastructure(BaseModel):
    ski_in_ski_out: Optional[bool] = None
    distance_to_airport_km: Optional[float] = Field(None, ge=0)
    family_friendly: Optional[bool] = None

class ResortModel(BaseModel):
    name: str
    country: str
    region: Optional[str] = None
    website: Optional[str] = None
    altitude: Optional[ResortAltitude] = Field(default_factory=ResortAltitude)
    trails: Optional[ResortTrails] = Field(default_factory=ResortTrails)
    prices: Optional[ResortPrices] = Field(default_factory=ResortPrices)
    infrastructure: Optional[ResortInfrastructure] = Field(default_factory=ResortInfrastructure)
    summary: Optional[str] = None


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


def init_db(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS resort (
            slug                  TEXT PRIMARY KEY,
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
    clean_name = re.sub(r'[^a-z0-9]', '', name.lower())
    clean_country = re.sub(r'[^a-z0-9]', '', country.lower())
    return f"{clean_country}_{clean_name}"

def save_to_db(resorts: List[ResortModel], source_url: str, db_path: str = DB_PATH) -> None:
    if not resorts:
        log_msg("DB", "No resorts found to save.")
        return

    conn = init_db(db_path)
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()

    # Get existing slugs to calculate new vs updated
    existing_slugs = {row[0] for row in cursor.execute("SELECT slug FROM resort").fetchall()}
    
    saved_count = 0
    new_count = 0
    updated_count = 0

    for r in resorts:
        slug = generate_slug(r.name, r.country)
        
        if slug in existing_slugs:
            updated_count += 1
        else:
            new_count += 1

        base_m     = r.altitude.base_m if r.altitude else None
        peak_m     = r.altitude.peak_m if r.altitude else None
        total_km   = r.trails.total_km if r.trails else None
        beg_pct    = r.trails.beginner_pct if r.trails else None
        price      = r.prices.day_pass_adult_eur if r.prices else None
        ski_in     = r.infrastructure.ski_in_ski_out if r.infrastructure else None
        airport_km = r.infrastructure.distance_to_airport_km if r.infrastructure else None

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
    log_msg("DB", f"Successfully saved {saved_count} resorts ({new_count} new, {updated_count} updated).")


def fetch_article(url: str) -> str:
    log_msg("FETCH", f"Downloading: {url}")
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        text = soup.get_text(separator="\n")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        clean_text = "\n".join(lines)
        
        log_msg("FETCH", f"Success! Got {len(clean_text)} characters of raw text.")
        return clean_text
    except Exception as e:
        log_msg("ERROR", f"Download failed: {e}")
        sys.exit(1)

def classify_with_openai(text: str, model: str, openai_url: str) -> str:
    max_chars = 8000
    if len(text) > max_chars:
        text = text[:max_chars].rsplit('.', 1)[0] + "."
        log_msg("AI", f"Text truncated to {len(text)} characters for context limits.")

    prompt = f"Extract resorts into JSON.\nSCHEMA:\n{SCHEMA_DESCRIPTION}\n\nTEXT:\n{text}"
    
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.0
    }

    log_msg("AI", f"Sending request to {model}...")
    start = time.time()
    try:
        resp = requests.post(f"{OPENAI_BASE_URL}/chat/completions", headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        
        response_data = resp.json()
        duration = time.time() - start
        
        # Extract token usage if available
        usage = response_data.get("usage", {})
        p_tokens = usage.get("prompt_tokens", 0)
        c_tokens = usage.get("completion_tokens", 0)
        
        log_msg("AI", f"Done in {duration:.1f}s. Tokens: {p_tokens} prompt / {c_tokens} completion.")
        return response_data["choices"][0]["message"]["content"]
        
    except requests.exceptions.HTTPError as e:
        log_msg("ERROR", f"API HTTP error: {e}. Response: {resp.text}")
        sys.exit(1)
    except Exception as e:
        log_msg("ERROR", f"API connection error: {e}")
        sys.exit(1)

def parse_and_validate(raw_llm_response: str) -> List[ResortModel]:
    cleaned = re.sub(r"```json|```", "", raw_llm_response).strip()
    
    try:
        data = json.loads(cleaned)
        resort_list = data.get("resorts", [])
        validated = []
        
        for item in resort_list:
            resort_name = item.get("name", "Unknown")
            try:
                validated.append(ResortModel(**item))
            except ValidationError as ve:
                # Flatten the error message for cleaner logs
                error_details = str(ve).replace('\n', ' | ')[:150]
                log_msg("VALID", f"Skipped resort '{resort_name}': {error_details}...")
                
        log_msg("VALID", f"Parsed JSON successfully. Found {len(validated)} valid resorts.")
        return validated
    except json.JSONDecodeError:
        log_msg("ERROR", "AI did not return valid JSON. Try again or check the model.")
        return []


def main():
    parser = argparse.ArgumentParser(description="Extract ski resort info from a URL using OpenAI API.")
    parser.add_argument("url", help="URL of the article or website to scan")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="The AI model name")
    args = parser.parse_args()

    page_text = fetch_article(args.url)
    raw_response = classify_with_openai(page_text, args.model)
    resorts = parse_and_validate(raw_response)
    save_to_db(resorts, source_url=args.url)

if __name__ == "__main__":
    main()
