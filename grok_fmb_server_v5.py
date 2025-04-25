import socket
import struct
import logging
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, jsonify, request
from threading import Thread

# Configure logging
logging.basicConfig(filename='fmb_server.log', level=logging.INFO,
                    format='%(asctime)s:%(levelname)s:%(message)s')

# Server configuration
HOST = '0.0.0.0'
PORT = 12345
FLASK_PORT = 5000
RESPONSE_TIMEOUT = 5  # Seconds to wait for device response

# SQLite database setup
DB_NAME = 'fmb_data.db'

# DOUT1 configuration
DOUT1_IO_ID = 179  # Adjust if your device uses a different IO ID for DOUT1
TIMEOUT_12H = 12 * 3600  # 12 hours in seconds
ACTIVATION_DURATION = 4000  # 4000 seconds

# Flask app
app = Flask(__name__)

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

def insert_gps_data(imei, timestamp, latitude, longitude, altitude, speed, angle, satellites, priority):
    dt = datetime.fromtimestamp(timestamp / 1000.0).strftime('%Y-%m-%d %H:%M:%S')
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO gps_data (imei, timestamp, latitude, longitude, altitude, speed, angle, satellites, priority) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
              (imei, dt, latitude, longitude, altitude, speed, angle, satellites, priority))
    conn.commit()
    conn.close()

def insert_io_data(imei, timestamp, io_id, io_value):
    dt = datetime.fromtimestamp(timestamp / 1000.0).strftime('%Y-%m-%d %H:%M:%S')
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO io_data (imei, timestamp, io_id, io_value) VALUES (?, ?, ?, ?)",
              (imei, dt, io_id, io_value))
    conn.commit()
    conn.close()
    return dt

def update_dout1_state(imei, dout1_value, timestamp_str, conn):
    """Update DOUT1 state and queue command, return command if needed"""
    conn_db = sqlite3.connect(DB_NAME)
    c = conn_db.cursor()
    c.execute("SELECT last_dout1_zero_time, dout1_active, deactivate_time FROM dout1_state WHERE imei = ?", (imei,))
    row = c.fetchone()

    now = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
    command = None
    if row:
        last_zero_time_str, dout1_active, deactivate_time_str = row
        if dout1_active == 1 and deactivate_time_str:
            deactivate_time = datetime.strptime(deactivate_time_str, '%Y-%m-%d %H:%M:%S')
            if now >= deactivate_time:
                command = "setdigout 0"
                # Only update state if command is successful
                if send_command_with_response(conn, command, imei):
                    c.execute("UPDATE dout1_state SET dout1_active = 0, deactivate_time = NULL WHERE imei = ?", (imei,))
                    logging.info(f"Deactivated DOUT1 for IMEI {imei}")

        if dout1_value == 0:
            if last_zero_time_str:
                last_zero_time = datetime.strptime(last_zero_time_str, '%Y-%m-%d %H:%M:%S')
                if (now - last_zero_time).total_seconds() > TIMEOUT_12H and dout1_active == 0:
                    command = "setdigout 1"
                    if send_command_with_response(conn, command, imei):
                        deactivate_time = now + timedelta(seconds=ACTIVATION_DURATION)
                        c.execute("UPDATE dout1_state SET dout1_active = 1, deactivate_time = ? WHERE imei = ?",
                                  (deactivate_time.strftime('%Y-%m-%d %H:%M:%S'), imei))
                        logging.info(f"Activated DOUT1 for IMEI {imei} for {ACTIVATION_DURATION} seconds")
            else:
                c.execute("UPDATE dout1_state SET last_dout1_zero_time = ? WHERE imei = ?",
                          (timestamp_str, imei))
        else:
            c.execute("UPDATE dout1_state SET last_dout1_zero_time = NULL WHERE imei = ?", (imei,))
    else:
        c.execute("INSERT INTO dout1_state (imei, last_dout1_zero_time, dout1_active, deactivate_time) VALUES (?, ?, 0, NULL)",
                  (imei, timestamp_str if dout1_value == 0 else None))
    conn_db.commit()
    conn_db.close()
    return command

def queue_command(imei, command):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    c.execute("INSERT INTO command_queue (imei, command, created_at, sent) VALUES (?, ?, ?, 0)",
              (imei, command, created_at))
    conn.commit()
    conn.close()
    logging.info(f"Queued command for IMEI {imei}: {command}")

def send_command_with_response(conn, command, imei):
    """Send command and wait for device response"""
    try:
        conn.sendall(command.encode('ascii') + b'\r\n')
        logging.info(f"Sent command to IMEI {imei}: {command}")
        
        # Set socket timeout for response
        conn.settimeout(RESPONSE_TIMEOUT)
        response = conn.recv(1024).decode('ascii').strip()
        
        # Check if response indicates success (adjust based on your device's response format)
        if 'OK' in response:
            logging.info(f"Command successful for IMEI {imei}: {response}")
            return True
        else:
            logging.error(f"Command failed for IMEI {imei}: {response}")
            return False
    except socket.timeout:
        logging.error(f"Timeout waiting for response from IMEI {imei} for command: {command}")
        return False
    except Exception as e:
        logging.error(f"Error sending command to IMEI {imei}: {e}")
        return False
    finally:
        conn.settimeout(None)  # Reset timeout

def send_queued_commands(conn, imei):
    conn_db = sqlite3.connect(DB_NAME)
    c = conn_db.cursor()
    c.execute("SELECT id, command FROM command_queue WHERE imei = ? AND sent = 0", (imei,))
    commands = c.fetchall()
    for cmd_id, command in commands:
        if send_command_with_response(conn, command, imei):
            c.execute("UPDATE command_queue SET sent = 1 WHERE id = ?", (cmd_id,))
            logging.info(f"Marked command {cmd_id} as sent for IMEI {imei}")
        else:
            logging.warning(f"Failed to execute queued command {cmd_id} for IMEI {imei}")
    conn_db.commit()
    conn_db.close()

def parse_avl_packet(data, imei, conn):
    offset = 0
    preamble = data[offset:offset+4]
    if preamble != b'\x00\x00\x00\x00':
        logging.warning(f"Invalid preamble: {preamble.hex()}")
        return 0
    offset += 4

    data_length = struct.unpack('>I', data[offset:offset+4])[0]
    offset += 4
    codec_id = data[offset]
    offset += 1
    
    if codec_id != 0x8E:
        logging.warning(f"Unsupported codec ID: {codec_id}")
        return 0

    number_of_data = struct.unpack('>H', data[offset:offset+2])[0]
    offset += 2

    logging.info(f"Parsing {number_of_data} records for IMEI: {imei}")

    for _ in range(number_of_data):
        timestamp = struct.unpack('>Q', data[offset:offset+8])[0]
        offset += 8
        priority = struct.unpack('>B', data[offset:offset+1])[0]
        offset += 1

        longitude = struct.unpack('>i', data[offset:offset+4])[0] / 10000000.0
        offset += 4
        latitude = struct.unpack('>i', data[offset:offset+4])[0] / 10000000.0
        offset += 4
        altitude = struct.unpack('>H', data[offset:offset+2])[0]
        offset += 2
        angle = struct.unpack('>H', data[offset:offset+2])[0]
        offset += 2
        satellites = struct.unpack('>B', data[offset:offset+1])[0]
        offset += 1
        speed = struct.unpack('>H', data[offset:offset+2])[0]
        offset += 2

        insert_gps_data(imei, timestamp, latitude, longitude, altitude, speed, angle, satellites, priority)

        event_io_id = struct.unpack('>H', data[offset:offset+2])[0]
        offset += 2
        total_io_count = struct.unpack('>H', data[offset:offset+2])[0]
        offset += 2

        dout1_value = None
        timestamp_str = None

        io_count_1b = struct.unpack('>H', data[offset:offset+2])[0]
        offset += 2
        for _ in range(io_count_1b):
            io_id = struct.unpack('>H', data[offset:offset+2])[0]
            offset += 2
            io_value = struct.unpack('>B', data[offset:offset+1])[0]
            offset += 1
            timestamp_str = insert_io_data(imei, timestamp, io_id, io_value)
            if io_id == DOUT1_IO_ID:
                dout1_value = io_value

        io_count_2b = struct.unpack('>H', data[offset:offset+2])[0]
        offset += 2
        for _ in range(io_count_2b):
            io_id = struct.unpack('>H', data[offset:offset+2])[0]
            offset += 2
            io_value = struct.unpack('>H', data[offset:offset+2])[0]
            offset += 2
            timestamp_str = insert_io_data(imei, timestamp, io_id, io_value)
            if io_id == DOUT1_IO_ID:
                dout1_value = io_value

        io_count_4b = struct.unpack('>H', data[offset:offset+2])[0]
        offset += 2
        for _ in range(io_count_4b):
            io_id = struct.unpack('>H', data[offset:offset+2])[0]
            offset += 2
            io_value = struct.unpack('>I', data[offset:offset+4])[0]
            offset += 4
            timestamp_str = insert_io_data(imei, timestamp, io_id, io_value)
            if io_id == DOUT1_IO_ID:
                dout1_value = io_value

        io_count_8b = struct.unpack('>H', data[offset:offset+2])[0]
        offset += 2
        for _ in range(io_count_8b):
            io_id = struct.unpack('>H', data[offset:offset+2])[0]
            offset += 2
            io_value = struct.unpack('>Q', data[offset:offset+8])[0]
            offset += 8
            timestamp_str = insert_io_data(imei, timestamp, io_id, io_value)
            if io_id == DOUT1_IO_ID:
                dout1_value = io_value

        io_count_xb = struct.unpack('>H', data[offset:offset+2])[0]
        offset += 2
        for _ in range(io_count_xb):
            io_id = struct.unpack('>H', data[offset:offset+2])[0]
            offset += 2
            io_length = struct.unpack('>H', data[offset:offset+2])[0]
            offset += 2
            io_value = int.from_bytes(data[offset:offset+io_length], byteorder='big')
            offset += io_length
            timestamp_str = insert_io_data(imei, timestamp, io_id, io_value)
            if io_id == DOUT1_IO_ID:
                dout1_value = io_value

        if dout1_value is not None and timestamp_str:
            command = update_dout1_state(imei, dout1_value, timestamp_str, conn)
            if command:
                queue_command(imei, command)  # Queue automatic commands

    number_of_data_end = struct.unpack('>H', data[offset:offset+2])[0]
    if number_of_data != number_of_data_end:
        logging.error(f"Number of data mismatch: Start={number_of_data}, End={number_of_data_end}")
    
    return number_of_data

# Flask API endpoints
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
        queue_command(imei, command)
        logging.info(f"Manual command queued for IMEI {imei}: {command}")
        conn.close()
        return jsonify({'command': command, 'status': 'queued'})
    conn.close()
    return jsonify({'error': 'IMEI not found'}), 404

def run_flask():
    app.run(host=HOST, port=FLASK_PORT, debug=False)

def main():
    create_db()
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen()
        logging.info(f"Server listening on {HOST}:{PORT}")
        logging.info(f"Flask API running on {HOST}:{FLASK_PORT}")

        while True:
            conn, addr = s.accept()
            logging.info(f"Connected by {addr}")
            try:
                imei_length = struct.unpack('>H', conn.recv(2))[0]
                imei = conn.recv(imei_length).decode('ascii').strip('\0')
                logging.info(f"IMEI received: {imei}")
                conn.sendall(b'\x01')

                # Send any queued commands
                send_queued_commands(conn, imei)

                data = conn.recv(4096)
                if data:
                    num_records = parse_avl_packet(data, imei, conn)
                    if num_records > 0:
                        conn.sendall(struct.pack('>I', num_records))
                    else:
                        logging.warning("No records parsed or unsupported codec")
            except Exception as e:
                logging.error(f"Error handling client: {e}")
            finally:
                conn.close()

if __name__ == "__main__":
    main()