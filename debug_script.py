import socket
import struct
import logging
import sqlite3

# Configure logging
logging.basicConfig(filename='debug_script.log', level=logging.INFO,
                    format='%(asctime)s:%(levelname)s:%(message)s')

# Server configuration
HOST = '0.0.0.0'  # Listen on all interfaces
PORT = 50122      # Choose your port

# SQLite database setup
DB_NAME = 'grok_fmb_data.db'

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
                  timestamp INTEGER,
                  io_id INTEGER,
                  io_value INTEGER)''')
    conn.commit()
    conn.close()

def insert_gps_data(imei, timestamp, latitude, longitude, altitude, speed, angle, satellites, priority):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO gps_data (imei, timestamp, latitude, longitude, altitude, speed, angle, satellites, priority) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
              (imei, timestamp, latitude, longitude, altitude, speed, angle, satellites, priority))
    conn.commit()
    conn.close()

def insert_io_data(imei, timestamp, io_id, io_value):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO io_data (imei, timestamp, io_id, io_value) VALUES (?, ?, ?, ?)",
              (imei, timestamp, io_id, io_value))
    conn.commit()
    conn.close()

def parse_avl_packet(data, imei):
    """Parse AVL data packet according to Teltonika Codec 8 Extended (8E) protocol"""
    
    offset = 0
    zero_byte = struct.unpack('>I', data[offset:offset+4])[0]
    logging.info(f"Zero byte {zero_byte}")
    offset += 4
    data_length = struct.unpack('>I', data[offset:offset+4])[0]  # Data field length
    logging.info(f"data_length:{data_length}")
    offset += 4
    codec_id = data[offset:offset+2]
    print(f"codec_id:{codec_id}.\noffset:{offset}")
    offset += 1
    
    if codec_id != 0x8E:  # Check for Codec 8E
        logging.warning(f"Unsupported codec ID: {codec_id}")
        return 0

    number_of_data = struct.unpack('>H', data[offset:offset+2])[0]  # 2-byte Number of Data
    offset += 2

    logging.info(f"Parsing {number_of_data} records for IMEI: {imei}")

    for _ in range(number_of_data):
        # AVL Data
        timestamp = struct.unpack('>Q', data[offset:offset+8])[0]  # 8-byte timestamp
        offset += 8
        priority = struct.unpack('>B', data[offset:offset+1])[0]   # 1-byte priority
        offset += 1

        # GPS Element
        longitude = struct.unpack('>i', data[offset:offset+4])[0] / 10000000.0  # 4-byte longitude
        offset += 4
        latitude = struct.unpack('>i', data[offset:offset+4])[0] / 10000000.0   # 4-byte latitude
        offset += 4
        altitude = struct.unpack('>H', data[offset:offset+2])[0]               # 2-byte altitude
        offset += 2
        angle = struct.unpack('>H', data[offset:offset+2])[0]                  # 2-byte angle
        offset += 2
        satellites = struct.unpack('>B', data[offset:offset+1])[0]             # 1-byte satellites
        offset += 1
        speed = struct.unpack('>H', data[offset:offset+2])[0]                  # 2-byte speed
        offset += 2

        # Insert GPS data
        insert_gps_data(imei, timestamp, latitude, longitude, altitude, speed, angle, satellites, priority)

        # IO Element (Codec 8E uses N of all elements followed by specific counts)
        event_io_id = struct.unpack('>H', data[offset:offset+2])[0]  # 2-byte Event IO ID
        offset += 2
        total_io_count = struct.unpack('>H', data[offset:offset+2])[0]  # 2-byte Total IO count
        offset += 2

        # 1-byte IO elements
        io_count_1b = struct.unpack('>H', data[offset:offset+2])[0]
        offset += 2
        for _ in range(io_count_1b):
            io_id = struct.unpack('>H', data[offset:offset+2])[0]
            offset += 2
            io_value = struct.unpack('>B', data[offset:offset+1])[0]
            offset += 1
            insert_io_data(imei, timestamp, io_id, io_value)

        # 2-byte IO elements
        io_count_2b = struct.unpack('>H', data[offset:offset+2])[0]
        offset += 2
        for _ in range(io_count_2b):
            io_id = struct.unpack('>H', data[offset:offset+2])[0]
            offset += 2
            io_value = struct.unpack('>H', data[offset:offset+2])[0]
            offset += 2
            insert_io_data(imei, timestamp, io_id, io_value)

        # 4-byte IO elements
        io_count_4b = struct.unpack('>H', data[offset:offset+2])[0]
        offset += 2
        for _ in range(io_count_4b):
            io_id = struct.unpack('>H', data[offset:offset+2])[0]
            offset += 2
            io_value = struct.unpack('>I', data[offset:offset+4])[0]
            offset += 4
            insert_io_data(imei, timestamp, io_id, io_value)

        # 8-byte IO elements
        io_count_8b = struct.unpack('>H', data[offset:offset+2])[0]
        offset += 2
        for _ in range(io_count_8b):
            io_id = struct.unpack('>H', data[offset:offset+2])[0]
            offset += 2
            io_value = struct.unpack('>Q', data[offset:offset+8])[0]
            offset += 8
            insert_io_data(imei, timestamp, io_id, io_value)

        # Variable length IO elements (X bytes)
        io_count_xb = struct.unpack('>H', data[offset:offset+2])[0]
        offset += 2
        for _ in range(io_count_xb):
            io_id = struct.unpack('>H', data[offset:offset+2])[0]
            offset += 2
            io_length = struct.unpack('>H', data[offset:offset+2])[0]  # Length of value
            offset += 2
            io_value = int.from_bytes(data[offset:offset+io_length], byteorder='big')
            offset += io_length
            insert_io_data(imei, timestamp, io_id, io_value)

    # Verify number of data at the end
    number_of_data_end = struct.unpack('>H', data[offset:offset+2])[0]
    if number_of_data != number_of_data_end:
        logging.error(f"Number of data mismatch: Start={number_of_data}, End={number_of_data_end}")
    
    return number_of_data

def main():
    create_db()
    
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen()
        logging.info(f"Debug Server Script listening on {HOST}:{PORT}")

        while True:
            conn, addr = s.accept()
            logging.info(f"Connected by {addr}")
            try:
                # Handle IMEI
                imei_length = struct.unpack('>H', conn.recv(2))[0]
                imei = conn.recv(imei_length).decode('ascii').strip('\0')
                logging.info(f"IMEI received: {imei}")
                conn.sendall(b'\x01')  # ACK IMEI

                # Handle AVL data
                data = conn.recv(4096)  # Buffer size to handle multiple records
                if data:
                    num_records = parse_avl_packet(data, imei)
                    if num_records > 0:
                        conn.sendall(struct.pack('>I', num_records))  # Send number of records as ACK
                    else:
                        logging.warning("No records parsed or unsupported codec")
            except Exception as e:
                logging.error(f"Error handling client: {e}")
            finally:
                conn.close()

if __name__ == "__main__":
    main()
