import json
import sys
import os
import shutil
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from db import get_stats, get_all_resorts, get_countries, DB_PATH, BASE_DIR
from utils import run_subprocess

app = Flask(__name__)

# Locate the enrichment script in the project directory
ENRICH_PY = str(BASE_DIR / "enrich.py")

@app.route("/")
def index():
    """Main dashboard showing the ski resort statistics and map/list."""
    stats = get_stats()
    resorts = get_all_resorts()
    countries = get_countries()
    return render_template(
        "index.html",
        resorts_json=json.dumps(resorts),
        total=stats["total"],
        complete=stats["complete"],
        countries_count=len(countries),
        countries=countries
    )

@app.route("/admin")
def admin():
    """Admin panel to trigger data collection and manage the list."""
    stats = get_stats()
    resorts = get_all_resorts()
    return render_template("admin.html", stats=stats, resorts=resorts)

@app.route('/admin/run/<cmd>')
def run_command(cmd):
    """Starts the background AI extraction process and streams logs to the browser."""
    if cmd == 'discover':
        # ИЗМЕНЕНО: Явно указываем пути к файлу целей и базе данных в папке /data
        command = [
            "python", "enrich.py", 
            "--file", "/data/targets.txt", 
            "--db", "/data/resorts.db"
        ]
    else:
        return "Unknown command", 400

    # Response is sent as a 'text/event-stream' so the user sees live logs
    return Response(
        stream_with_context(run_subprocess(command)), 
        mimetype='text/event-stream',
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )

@app.route('/admin/save_targets', methods=['POST'])
def save_targets():
    """Saves the list of resort names from the web interface to a text file."""
    data = request.json
    targets_text = data.get('targets', '')
    
    # ИЗМЕНЕНО: Сохраняем в разрешенную для записи папку /data
    with open('/data/targets.txt', 'w', encoding='utf-8') as f:
        f.write(targets_text)
        
    return jsonify({"status": "success"})

if __name__ == "__main__":
    # ИЗМЕНЕНО: Логика инициализации базы данных прямо в Python
    if not os.path.exists("/data/resorts.db"):
        print("База данных не найдена в /data — копируем seed...")
        os.makedirs("/data", exist_ok=True)
        shutil.copy2("/app/data-seed/resorts.db", "/data/resorts.db")
        print("База данных успешно скопирована.")
    else:
        print("Используется существующая база данных в /data.")

    # Используем порт 5000 по рекомендации учителя
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)