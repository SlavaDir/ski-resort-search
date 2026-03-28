# Ski Resort Data Aggregator

A local AI-powered tool for discovering, extracting, and aggregating structured data about ski resorts from the web. This project uses web scraping combined with a local LLM (via Ollama) to parse unstructured text into a clean SQLite database and visualizes it using a Flask web interface.

## Features

* **AI Data Extraction**: Uses a local Ollama model (default: `qwen2.5:3b`) to read articles and extract specific data points (altitude, trail statistics, prices, infrastructure).
* **Automated Discovery**: Automatically searches Wikipedia and DuckDuckGo for ski resorts based on a list of names.
* **Data Validation**: Enforces strict data schemas using Pydantic to ensure the AI doesn't hallucinate invalid numbers (e.g., negative prices or impossible mountain heights).
* **Web Dashboard**: A Flask-based web UI to view statistics, browse the database, and trigger new data collection tasks directly from your browser with real-time log streaming.
* **Local**: All AI processing is done locally on your machine. No paid API keys are required.

## Project Structure

* `app.py`: The core extraction script. Downloads a specific URL, cleans the HTML, and passes the text to Ollama for JSON extraction. Saves the results to `resorts.db`.
* `enrich.py`: The discovery script. Takes a list of resort names, searches the web (Wikipedia & DuckDuckGo) for context, and uses `app.py`'s logic to extract and save the data.
* `server.py`: The Flask web server. Serves the user dashboard and the admin panel.
* `utils.py`: Helper functions to run the background Python scripts and stream their output live to the web interface.

## Prerequisites

Before running the project, you need to have the following installed:

1. **Python 3.8+**
2. **Ollama**: Download and install from [ollama.com](https://ollama.com/).
3. **Local AI Model**: Pull the default model (or change it in the scripts).
   ```bash
   ollama run qwen2.5:3b
   ```

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/SlavaDir/ski-resort-search.git
   cd ski-resort-aggregator
   ```

2. Install the required Python dependencies:
   ```bash
   pip install requests beautifulsoup4 pydantic flask
   ```

## Usage

### 1. Web Interface 
Start the Flask server to access the dashboard and admin panel:
   ```bash
   python server.py
   ```
* **Dashboard**: Open `http://localhost:5001/` in your browser to view the collected resorts.
* **Admin Panel**: Open `http://localhost:5001/admin` to manage target resorts and start the background discovery process.

### 2. CLI: Single URL Parsing
If you want to extract data from a specific article manually:
   ```bash
   python app.py [https://example.com/best-ski-resorts-in-france](https://example.com/best-ski-resorts-in-france)
   ```

### 3. Command Line: Bulk Discovery
If you have a text file (`targets.txt`) with a list of resort names (one per line), you can run the enrichment script directly:
   ```bash
   python enrich.py --file targets.txt
   ```

## Database

The extracted data is automatically saved to a local SQLite database named `resorts.db`. The script uses "Upsert" logic, meaning if a resort already exists, it will update the missing fields without creating duplicates.