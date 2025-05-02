import socket
import struct
import logging
import sqlite3
from datetime import datetime, timedelta,timezone
import crcmod
import requests

# Configure logging
logging.basicConfig(filename='grok_tcp_server_v6.log', level=logging.INFO,
                    format='%(asctime)s:%(levelname)s:%(message)s')

# Server configuration
version="6.5"
HOST = '127.0.0.1'  # Localhost for cron
PORT = 12345
DB_NAME = 'grok_fmb_data_v6.db'
DOUT1_IO_ID = 179
TIMEOUT_12H = 12 * 3600
ACTIVATION_DURATION = 4000
RESPONSE_TIMEOUT = 5
crc16 = crcmod.mkCrcFun(0x18005, initCrc=0x0000, rev=False)

def insert_gps_data(imei, timestamp, latitude, longitude, altitude, speed, angle, satellites, priority):
    dt = datetime.fromtimestamp(timestamp / 1000.0).strftime('%Y-%m-%d %H:%M:%S')
    logging.info(f"Inserting gps_data for IMEI {imei}: timestamp={dt}")
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO gps_data (imei, timestamp, latitude, longitude, altitude, speed, angle, satellites, priority) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
              (imei, dt, latitude, longitude, altitude, speed, angle, satellites, priority))
    conn.commit()
    conn.close()

def insert_io_data(imei, timestamp, io_id, io_value):
    dt = datetime.fromtimestamp(timestamp / 1000.0).strftime('%Y-%m-%d %H:%M:%S')
    logging.info(f"Inserting io_data for IMEI {imei}: timestamp={dt}, io_id={io_id}")
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO io_data (imei, timestamp, io_id, io_value) VALUES (?, ?, ?, ?)",
              (imei, dt, io_id, io_value))
    conn.commit()
    conn.close()
    return dt

def update_dout1_state(imei, dout1_value, timestamp_str, conn):
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

def build_codec12_packet(command):
    command_bytes = command.encode('ascii')
    command_length = len(command_bytes)
    data_field = struct.pack('>BBBI', 0x0C, 0x01, 0x05, command_length) + command_bytes + struct.pack('>B', 0x01)
    crc = crc16(data_field)
    packet = struct.pack('>I', 0) + struct.pack('>I', len(data_field)) + data_field + struct.pack('>I', crc)
    return packet

def parse_codec12_response(data):
    if len(data) < 14:
        logging.error("Response too short")
        return None
    offset = 0
    preamble = struct.unpack('>I', data[offset:offset+4])[0]
    if preamble != 0:
        logging.error(f"Invalid preamble: {preamble}")
        return None
    offset += 4
    data_length = struct.unpack('>I', data[offset:offset+4])[0]
    offset += 4
    codec_id = data[offset]
    if codec_id != 0x0C:
        logging.error(f"Invalid codec ID: {codec_id}")
        return None
    offset += 1
    quantity1 = data[offset]
    offset += 1
    response_type = data[offset]
    if response_type != 0x06:
        logging.error(f"Invalid response type: {response_type}")
        return None
    offset += 1
    response_length = struct.unpack('>I', data[offset:offset+4])[0]
    offset += 4
    response = data[offset:offset+response_length].decode('ascii')
    offset += response_length
    quantity2 = data[offset]
    if quantity1 != quantity2:
        logging.error(f"Quantity mismatch: {quantity1} != {quantity2}")
        return None
    return response

def send_command_with_response(conn, command, imei):
    try:
        packet = build_codec12_packet(command)
        conn.sendall(packet)
        logging.info(f"Sent Codec 12 command to IMEI {imei}: {command}")
        conn.settimeout(RESPONSE_TIMEOUT)
        response_data = conn.recv(1024)
        response = parse_codec12_response(response_data)
        if response and 'OK' in response:
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
        conn.settimeout(None)

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

def parse_timestamp(data, offset, length=8):
    try:
        # Validate data length
        if len(data[offset:offset+length]) != length:
            logging.error(f"Insufficient data for timestamp at offset {offset}, length {length}, packet: {data.hex()}")
            return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')  # Fallback to server GMT
        # Convert bytes to integer
        timestamp_ms = int.from_bytes(data[offset:offset+length], byteorder='big')
        # Validate type
        if not isinstance(timestamp_ms, int):
            logging.error(f"timestamp_ms is not an integer: {type(timestamp_ms)} {timestamp_ms}")
            return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')  # Fallback to server GMT
        # Convert to seconds
        timestamp_s = timestamp_ms / 1000.0
        # Validate range (1970 to 2038)
        epoch_start = 0  # 1970-01-01
        epoch_end = 2147483647  # 2038-01-19
        if timestamp_s < epoch_start or timestamp_s > epoch_end:
            logging.error(f"Invalid timestamp_ms: {timestamp_ms} (seconds: {timestamp_s}), out of range")
            return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')  # Fallback to server GMT
        # Convert to datetime
        timestamp = datetime.fromtimestamp(timestamp_s)
        formatted_timestamp = timestamp.strftime('%Y-%m-%d %H:%M:%S')
        logging.debug(f"Parsed timestamp: {formatted_timestamp} from {timestamp_ms}ms")
        return formatted_timestamp
    except Exception as e:
        logging.error(f"Failed to parse timestamp at offset {offset}: {e}, raw data: {data[offset:offset+length].hex()}, full packet: {data.hex()}")
        return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')  # Fallback to server GMT


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
    records =[]
    for _ in range(number_of_data):
        timestamp = parse_timestamp(data, offset)
        offset += 8
        if not timestamp:
          logging.error("Skipping record due to invalid timestamp")
          continue
       
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
        record = {
                'timestamp': timestamp,
                'latitude': latitude,
                'longitude': longitude,
                'altitude': altitude,
                'speed': speed,
                'angle': angle,
                'satellites': satellites,
                'priority': priority,
                'io_data': []
            }
        #insert_gps_data(imei, timestamp, latitude, longitude, altitude, speed, angle, satellites, priority)
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
            #timestamp_str = insert_io_data(imei, timestamp, io_id, io_value)
            record['io_data'].append({'io_id': io_id, 'io_value': io_value})
            if io_id == DOUT1_IO_ID:
                dout1_value = io_value
        io_count_2b = struct.unpack('>H', data[offset:offset+2])[0]
        offset += 2
        for _ in range(io_count_2b):
            io_id = struct.unpack('>H', data[offset:offset+2])[0]
            offset += 2
            io_value = struct.unpack('>H', data[offset:offset+2])[0]
            offset += 2
            record['io_data'].append({'io_id': io_id, 'io_value': io_value})
            #timestamp_str = insert_io_data(imei, timestamp, io_id, io_value)
            if io_id == DOUT1_IO_ID:
                dout1_value = io_value
        io_count_4b = struct.unpack('>H', data[offset:offset+2])[0]
        offset += 2
        for _ in range(io_count_4b):
            io_id = struct.unpack('>H', data[offset:offset+2])[0]
            offset += 2
            io_value = struct.unpack('>I', data[offset:offset+4])[0]
            offset += 4
            record['io_data'].append({'io_id': io_id, 'io_value': io_value})
            #timestamp_str = insert_io_data(imei, timestamp, io_id, io_value)
            if io_id == DOUT1_IO_ID:
                dout1_value = io_value
        io_count_8b = struct.unpack('>H', data[offset:offset+2])[0]
        offset += 2
        for _ in range(io_count_8b):
            io_id = struct.unpack('>H', data[offset:offset+2])[0]
            offset += 2
            io_value = struct.unpack('>Q', data[offset:offset+8])[0]
            offset += 8
            record['io_data'].append({'io_id': io_id, 'io_value': io_value})
            #timestamp_str = insert_io_data(imei, timestamp, io_id, io_value)
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
            record['io_data'].append({'io_id': io_id, 'io_value': io_value})
            #timestamp_str = insert_io_data(imei, timestamp, io_id, io_value)
            if io_id == DOUT1_IO_ID:
                dout1_value = io_value
        records.append(record)
        """ if dout1_value is not None and timestamp_str:
            command = update_dout1_state(imei, dout1_value, timestamp_str, conn)
            if command:
                conn_db = sqlite3.connect(DB_NAME)
                c = conn_db.cursor()
                created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                c.execute("INSERT INTO command_queue (imei, command, created_at, sent) VALUES (?, ?, ?, 0)",
                          (imei, command, created_at))
                conn_db.commit()
                conn_db.close()
                logging.info(f"Queued command for IMEI {imei}: {command}") """
    payload = {'imei': imei, 'records': records}
    try:
            response = requests.post("http://iot.satgroupe.com/syncing_data", json=payload, timeout=10)
            response.raise_for_status()
            logging.info(f"Sent data to API for IMEI {imei}: {response.json()}")
    except requests.RequestException as e:
            logging.error(f"Failed to send data to API for IMEI {imei}: {e}")

    number_of_data_end = struct.unpack('>H', data[offset:offset+2])[0]
    
    if number_of_data != number_of_data_end:
        logging.error(f"Number of data mismatch: Start={number_of_data}, End={number_of_data_end}")
    return number_of_data

def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((HOST, PORT))
            s.listen()
            logging.info(f"TCP server started on {HOST}:{PORT}")
            s.settimeout(540)  # Run for 540 seconds max
            conn, addr = s.accept()
            logging.info(f"Connected by {addr}")
            try:
                imei_length = struct.unpack('>H', conn.recv(2))[0]
                imei = conn.recv(imei_length).decode('ascii').strip('\0')
                logging.info(f"IMEI received: {imei}")
                conn.sendall(b'\x01')
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
        except socket.timeout:
            logging.info("TCP server timeout, exiting")
        except Exception as e:
            logging.error(f"TCP server error: {e}")

if __name__ == "__main__":
    main()