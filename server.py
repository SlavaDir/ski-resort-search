import json
import sys
import os
import shutil
from functools import wraps
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from db import get_stats, get_all_resorts, get_countries, DB_PATH, BASE_DIR
from utils import run_subprocess

app = Flask(__name__)

"""
SECURITY SETTINGS
Credentials are retrieved from environment variables for better security.
"""
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")

"""
DOS PROTECTION
Limit the maximum allowed payload to 1 MB to prevent memory exhaustion.
"""
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024 

def check_auth(username, password):
    """
    Verifies if the provided credentials match the administrative settings.
    """
    return username == ADMIN_USERNAME and password == ADMIN_PASSWORD

def authenticate():
    """
    Sends a 401 response that enables basic access authentication in the browser.
    """
    return Response(
        'Access denied. Please provide valid credentials.\n', 401,
        {'WWW-Authenticate': 'Basic realm="Admin Login Required"'}
    )

def requires_auth(f):
    """
    Decorator to protect administrative routes using Basic HTTP Authentication.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

ENRICH_PY = str(BASE_DIR / "enrich.py")

@app.route("/")
def index():
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
@requires_auth
def admin():
    stats = get_stats()
    resorts = get_all_resorts()
    return render_template("admin.html", stats=stats, resorts=resorts)

@app.route('/admin/run/<cmd>')
@requires_auth
def run_command(cmd):
    """
    Starts the background AI extraction process and streams logs to the browser.
    Uses persistent storage paths in the /data directory.
    """
    if cmd == 'discover':
        """
        Execute the enrichment script with explicit paths to targets and database.
        """
        command = [
            "python", "enrich.py", 
            "--file", "/data/targets.txt", 
            "--db", "/data/resorts.db"
        ]
    else:
        return "Unknown command", 400

    return Response(
        stream_with_context(run_subprocess(command)), 
        mimetype='text/event-stream',
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )

@app.route('/admin/save_targets', methods=['POST'])
@requires_auth
def save_targets():
    """
    Saves the list of resort names from the web interface to a text file in /data.
    Includes a server-side length check for additional safety.
    """
    data = request.json
    targets_text = data.get('targets', '')
    
    if len(targets_text) > 500000:
        return jsonify({"status": "error", "message": "Payload too large"}), 400

    with open('/data/targets.txt', 'w', encoding='utf-8') as f:
        f.write(targets_text)
        
    return jsonify({"status": "success"})

if __name__ == "__main__":
    """
    Ensures the production database exists in the /data volume.
    Copies the initial seed database if the file is missing.
    """
    if not os.path.exists("/data/resorts.db"):
        print("[INFO] Database not found in /data - copying seed...")
        os.makedirs("/data", exist_ok=True)
        shutil.copy2("/app/data-seed/resorts.db", "/data/resorts.db")
        print("[OK] Database successfully initialized.")
    else:
        print("[INFO] Using existing database in /data.")

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
