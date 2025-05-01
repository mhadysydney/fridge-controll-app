import logging
import sqlite3
from flask import Flask, jsonify, request
from datetime import datetime

# Configure logging
logging.basicConfig(filename='flask_server.log', level=logging.INFO,
                    format='%(asctime)s:%(levelname)s:%(message)s')

# SQLite database
DB_NAME = 'grok_fmb_data_v6.db'

# Flask app
app = Flask(__name__)
application = app  # Required for cPanel's Passenger WSGI

def create_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS gps_data
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  imei TEXT,
                  timestamp TEXT,
                  latitude REAL,
                  longitude REAL,
                  altitude INTEGER,
                  speed REAL,
                  angle REAL,
                  satellites INTEGER,
                  priority INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS io_data
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  imei TEXT,
                  timestamp TEXT,
                  io_id INTEGER,
                  io_value INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS dout1_state
                 (imei TEXT PRIMARY KEY,
                  last_dout1_zero_time TEXT,
                  dout1_active INTEGER,
                  deactivate_time TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS command_queue
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  imei TEXT,
                  command TEXT,
                  created_at TEXT,
                  sent INTEGER DEFAULT 0)''')
    conn.commit()
    conn.close()

@app.route('/dout1_status/<imei>', methods=['GET'])
def get_dout1_status(imei):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT dout1_active, deactivate_time FROM dout1_state WHERE imei = ?", (imei,))
    row = c.fetchone()
    conn.close()
    if row:
        dout1_active, deactivate_time = row
        return jsonify({
            'imei': imei,
            'dout1_active': bool(dout1_active),
            'deactivate_time': deactivate_time
        })
    return jsonify({'error': 'IMEI not found'}), 404

@app.route('/dout1_control/<imei>', methods=['POST'])
def control_dout1(imei):
    data = request.json
    activate = data.get('activate')
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT dout1_active FROM dout1_state WHERE imei = ?", (imei,))
    row = c.fetchone()
    if row:
        command = "setdigout 1" if activate else "setdigout 0"
        created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        c.execute("INSERT INTO command_queue (imei, command, created_at, sent) VALUES (?, ?, ?, 0)",
                  (imei, command, created_at))
        conn.commit()
        logging.info(f"Manual command queued for IMEI {imei}: {command}")
        conn.close()
        return jsonify({'command': command, 'status': 'queued'})
    conn.close()
    return jsonify({'error': 'IMEI not found'}), 404

@app.route('/', methods=['GET'])
def welcome_route():
    
    return jsonify({
            'message': "Welcome to my flask api server!",
        })

if __name__ == "__main__":
    create_db()
    app.run()