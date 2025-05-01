from flask import Flask, jsonify, request
from flask_cors import CORS
import sqlite3
import os,sys
import logging
from datetime import datetime

app = Flask(__name__)
CORS(app)  # Enable CORS for Quasar frontend

DB_NAME = 'grok_fmb_data_v6.db'
LOG_FILE = 'api_server.log'

# Configure logging
try:
    log_dir = os.path.dirname(LOG_FILE)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, mode=0o755)
    logging.basicConfig(
        filename=LOG_FILE,
        level=logging.DEBUG,
        format='%(asctime)s:%(levelname)s:%(message)s'
    )
    logging.info("API logging initialized")
except Exception as e:
    logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)
    logging.error(f"Failed to initialize API logging: {e}")

def initialize_database():
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS gps_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            imei TEXT,
            timestamp TEXT,
            latitude REAL,
            longitude REAL,
            altitude INTEGER,
            speed INTEGER,
            angle INTEGER,
            satellites INTEGER,
            priority INTEGER
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS io_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            imei TEXT,
            timestamp TEXT,
            io_id INTEGER,
            io_value INTEGER
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS dout1_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            imei TEXT UNIQUE,
            dout1_active INTEGER,
            deactivate_time TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS command_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            imei TEXT,
            command TEXT,
            status TEXT,
            created_at TEXT
        )''')
        conn.commit()
        conn.close()
        logging.info("Database initialized")
    except Exception as e:
        logging.error(f"Failed to initialize database: {e}")
        raise

# Initialize database if missing
if not os.path.exists(DB_NAME):
    initialize_database()
    logging.info("Database recreated due to ephemeral storage")

@app.route('/debug', methods=['GET'])
def debug():
    try:
        test_file = 'test.txt'
        with open(test_file, 'w') as f:
            f.write('Test file created')
        os.chmod(test_file, 0o666)

        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in c.fetchall()]
        conn.close()

        response = {
            'status': 'Debug successful',
            'log_file_exists': os.path.exists(LOG_FILE),
            'db_file_exists': os.path.exists(DB_NAME),
            'test_file_exists': os.path.exists(test_file),
            'tables': tables
        }
        logging.info("Debug endpoint accessed")
        return jsonify(response)
    except Exception as e:
        logging.error(f"Debug endpoint failed: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/dout1_status/<imei>', methods=['GET'])
def dout1_status(imei):
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute('SELECT dout1_active, deactivate_time FROM dout1_state WHERE imei = ?', (imei,))
        row = c.fetchone()
        conn.close()

        if row:
            response = {
                'imei': imei,
                'dout1_active': bool(row[0]),
                'deactivate_time': row[1]
            }
            logging.info(f"DOUT1 status retrieved for IMEI {imei}")
            return jsonify(response)
        else:
            logging.warning(f"IMEI {imei} not found in dout1_status")
            return jsonify({'error': 'IMEI not found'}), 404
    except Exception as e:
        logging.error(f"Error in dout1_status for IMEI {imei}: {e}")
        return jsonify({'error': 'Server error'}), 500

@app.route('/dout1_control/<imei>', methods=['POST'])
def dout1_control(imei):
    try:
        data = request.get_json()
        if not data or 'activate' not in data:
            logging.warning(f"Invalid input for dout1_control, IMEI {imei}")
            return jsonify({'error': 'Invalid input'}), 400

        activate = data['activate']
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute('SELECT dout1_active FROM dout1_state WHERE imei = ?', (imei,))
        row = c.fetchone()

        if row:
            command = 'setdigout 1' if activate else 'setdigout 0'
            created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            c.execute('INSERT INTO command_queue (imei, command, status, created_at) VALUES (?, ?, ?, ?)',
                      (imei, command, 'pending', created_at))
            conn.commit()
            conn.close()
            logging.info(f"Command queued for IMEI {imei}: {command}")
            return jsonify({'command': command, 'status': 'queued'})
        else:
            conn.close()
            logging.warning(f"IMEI {imei} not found in dout1_control")
            return jsonify({'error': 'IMEI not found'}), 404
    except Exception as e:
        logging.error(f"Error in dout1_control for IMEI {imei}: {e}")
        return jsonify({'error': 'Server error'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)