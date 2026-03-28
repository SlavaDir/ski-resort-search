import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).parent
DB_PATH = str(BASE_DIR / "resorts.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_all_resorts(filters=None):
    conn = get_db()
    cur = conn.cursor()
    query = """
        SELECT slug, name, country, region,
               base_m, peak_m, total_km, beginner_pct,
               day_pass_adult_eur, ski_in_ski_out,
               distance_to_airport_km, summary, updated_at
        FROM resort WHERE 1=1
    """
    params = []
    if filters:
        if filters.get("country"):
            query += " AND LOWER(country) = LOWER(?)"
            params.append(filters["country"])
        if filters.get("max_price"):
            query += " AND (day_pass_adult_eur IS NULL OR day_pass_adult_eur <= ?)"
            params.append(float(filters["max_price"]))
        # ... остальные фильтры как в оригинале ...
    
    query += " ORDER BY name ASC"
    cur.execute(query, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

def get_stats():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as total FROM resort")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) as complete FROM resort WHERE base_m IS NOT NULL AND peak_m IS NOT NULL AND total_km IS NOT NULL AND day_pass_adult_eur IS NOT NULL")
    complete = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT country) as countries FROM resort")
    countries = cur.fetchone()[0]
    conn.close()
    return {"total": total, "complete": complete, "incomplete": total - complete, "countries": countries}

def get_countries():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT country FROM resort WHERE country IS NOT NULL ORDER BY country")
    rows = [r[0] for r in cur.fetchall()]
    conn.close()
    return rows