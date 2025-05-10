import logging
import socket
import struct
from datetime import datetime, timezone
import crcmod
import requests

# Configure logging
logging.basicConfig(filename='tcp_server_debug_v8.log', level=logging.INFO,
                    format='%(asctime)s:%(levelname)s:%(message)s')

# Server configuration
version = "8.0"
HOST = '127.0.0.1'  # Localhost for cron
PORT = 50122
API_URL = 'https://iot.satgroupe.com'  # Adjust to your cPanel subdomain
SYNC_DATA_URL = f'{API_URL}/syncing_data'
COMMAND_QUEUE_URL = f'{API_URL}/command_queue'
RESPONSE_TIMEOUT = 5
DOUT1_IO_ID = 179  # Added for DOUT1 control (from old script)
POWER_IO_ID = 66   # Power status (from prior context)
TIMEOUT_12H = 12 * 3600
ACTIVATION_DURATION = 4000
crc16 = crcmod.mkCrcFun(0x18005, initCrc=0x0000, rev=False)  # Updated to old script's CRC config

def verify_crc(data, expected_crc):
    calculated_crc = crc16(data)
    return calculated_crc == expected_crc

def parse_timestamp(data, offset, length=8):
    try:
        print(f"timestamp: {data[offset:offset+length]}")
        if len(data[offset:offset+length]) != length:
            logging.error(f"Insufficient data for timestamp at offset {offset}, length {length}, packet: {data.hex()}")
            return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        timestamp_ms = int.from_bytes(data[offset:offset+length], byteorder='big')
        if not isinstance(timestamp_ms, int):
            logging.error(f"timestamp_ms is not an integer: {type(timestamp_ms)} {timestamp_ms}")
            return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        timestamp_s = timestamp_ms / 1000.0
        epoch_start = 0
        epoch_end = 2147483647
        if timestamp_s < epoch_start or timestamp_s > epoch_end:
            logging.error(f"Invalid timestamp_ms: {timestamp_ms} (seconds: {timestamp_s}), packet: {data.hex()}")
            return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        timestamp = datetime.fromtimestamp(timestamp_s, tz=timezone.utc)
        formatted_timestamp = timestamp.strftime('%Y-%m-%d %H:%M:%S')
        logging.debug(f"Parsed timestamp: {formatted_timestamp} from {timestamp_ms}ms")
        return formatted_timestamp
    except Exception as e:
        logging.error(f"Failed to parse timestamp at offset {offset}: {e}, raw data: {data[offset:offset+length].hex()}, full packet: {data.hex()}")
        return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

def build_codec12_packet(command):
    command_bytes = command.encode('ascii')
    command_length = len(command_bytes)
    data_field = struct.pack('>BBBI', 0x0C, 0x01, 0x05, command_length) + command_bytes + struct.pack('>B', 0x01)
    crc = crc16(data_field)
    packet = struct.pack('>I', 0) + struct.pack('>I', len(data_field)) + data_field + struct.pack('>I', crc)
    return packet

def parse_codec12_response(data):
    try:
        if len(data) < 14:
            logging.error(f"Codec 12 response too short: {len(data)} bytes, packet: {data.hex()}")
            return None
        offset = 0
        preamble = struct.unpack('>I', data[offset:offset+4])[0]
        if preamble != 0:
            logging.error(f"Invalid preamble: {preamble}, packet: {data.hex()}")
            return None
        offset += 4
        data_length = struct.unpack('>I', data[offset:offset+4])[0]
        offset += 4
        codec_id = data[offset]
        if codec_id != 0x0C:
            logging.error(f"Invalid codec ID: {codec_id}, packet: {data.hex()}")
            return None
        offset += 1
        quantity1 = data[offset]
        offset += 1
        response_type = data[offset]
        if response_type != 0x06:
            logging.error(f"Invalid response type: {response_type}, packet: {data.hex()}")
            return None
        offset += 1
        response_length = struct.unpack('>I', data[offset:offset+4])[0]
        offset += 4
        response = data[offset:offset+response_length].decode('ascii', errors='ignore')
        offset += response_length
        quantity2 = data[offset]
        if quantity1 != quantity2:
            logging.error(f"Quantity mismatch: {quantity1} != {quantity2}, packet: {data.hex()}")
            return None
        crc = struct.unpack('>I', data[offset+1:offset+5])[0]
        if not verify_crc(data[8:offset+1], crc):
            logging.error(f"CRC check failed for Codec 12 response, packet: {data.hex()}")
            return None
        logging.info(f"Parsed Codec 12 response: type={response_type}, data='{response}'")
        return response
    except Exception as e:
        logging.error(f"Failed to parse Codec 12 response: {e}, packet: {data.hex()}")
        return None

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
    try:
        response = requests.get(f"{COMMAND_QUEUE_URL}/{imei}", timeout=10)
        response.raise_for_status()
        commands = response.json().get('commands', [])
        logging.debug(f"Fetched {len(commands)} pending commands for IMEI {imei}")
        for command_entry in commands:
            command_id = command_entry['id']
            command = command_entry['command']
            if send_command_with_response(conn, command, imei):
                try:
                    requests.post(f"{COMMAND_QUEUE_URL}/update/{command_id}", json={'status': 'completed'}, timeout=10)
                    logging.info(f"Command {command_id} ('{command}') marked as completed for IMEI {imei}")
                except requests.RequestException as e:
                    logging.error(f"Failed to update command {command_id} status: {e}")
            else:
                logging.error(f"Command {command_id} ('{command}') failed for IMEI {imei}")
    except requests.RequestException as e:
        logging.error(f"Failed to fetch queued commands for IMEI {imei}: {e}")

def parse_avl_packet(data, imei, conn):
    try:
        offset = 0
        preamble = data[offset:offset+4]
        if preamble != b'\x00\x00\x00\x00':
            logging.warning(f"Invalid preamble: {preamble.hex()}, packet: {data.hex()}")
            return 0
        offset += 4
        data_length = struct.unpack('>I', data[offset:offset+4])[0]
        logging.info(f"data_length:{data_length}")
        offset += 4
        codec_id = data[offset]
        offset += 1
        if codec_id != 0x8E:
            logging.warning(f"Unsupported codec ID: {codec_id}, codec ID_HEX: {codec_id.hex()}")
            return 0
        print(f"data: {data[offset]}")
        number_of_data =data[offset]
        
        logging.info(f"Parsing {number_of_data} records for IMEI: {imei}, codec: {codec_id}")

        # Verify CRC
        """ crc = struct.unpack('>I', data[-4:])[0]
        if not verify_crc(data[4:-4], crc):
            logging.error(f"CRC check failed, packet: {data.hex()}")
            return 0 """
        offset += 1
        records = []
        for _ in range(number_of_data):
            if offset + 8 > len(data) - 4:
                logging.error(f"Insufficient data for timestamp in record {_+1}, packet: {data.hex()}")
                break

            timestamp = parse_timestamp(data, offset)
            offset += 8
            if not timestamp:
                logging.error(f"Skipping record due to invalid timestamp, packet: {data.hex()}")
                continue

            if offset + 16 > len(data) - 4:
                logging.error(f"Insufficient data for GPS in record {_+1}, packet: {data.hex()}")
                break

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

            if offset + 4 > len(data) - 4:
                logging.error(f"Insufficient data for IO in record {_+1}, packet: {data.hex()}")
                break

            event_io_id = struct.unpack('>H', data[offset:offset+2])[0]
            offset += 2
            total_io_count = struct.unpack('>H', data[offset:offset+2])[0]
            offset += 2

            io_count_1b = struct.unpack('>H', data[offset:offset+2])[0]
            offset += 2
            for _ in range(io_count_1b):
                if offset + 3 > len(data) - 4:
                    logging.error(f"Insufficient data for 1-byte IO in record {_+1}, packet: {data.hex()}")
                    break
                io_id = struct.unpack('>H', data[offset:offset+2])[0]
                offset += 2
                io_value = struct.unpack('>B', data[offset:offset+1])[0]
                offset += 1
                record['io_data'].append({'io_id': io_id, 'io_value': io_value})

            io_count_2b = struct.unpack('>H', data[offset:offset+2])[0]
            offset += 2
            for _ in range(io_count_2b):
                if offset + 4 > len(data) - 4:
                    logging.error(f"Insufficient data for 2-byte IO in record {_+1}, packet: {data.hex()}")
                    break
                io_id = struct.unpack('>H', data[offset:offset+2])[0]
                offset += 2
                io_value = struct.unpack('>H', data[offset:offset+2])[0]
                offset += 2
                record['io_data'].append({'io_id': io_id, 'io_value': io_value})

            io_count_4b = struct.unpack('>H', data[offset:offset+2])[0]
            offset += 2
            for _ in range(io_count_4b):
                if offset + 6 > len(data) - 4:
                    logging.error(f"Insufficient data for 4-byte IO in record {_+1}, packet: {data.hex()}")
                    break
                io_id = struct.unpack('>H', data[offset:offset+2])[0]
                offset += 2
                io_value = struct.unpack('>I', data[offset:offset+4])[0]
                offset += 4
                record['io_data'].append({'io_id': io_id, 'io_value': io_value})

            io_count_8b = struct.unpack('>H', data[offset:offset+2])[0]
            offset += 2
            for _ in range(io_count_8b):
                if offset + 10 > len(data) - 4:
                    logging.error(f"Insufficient data for 8-byte IO in record {_+1}, packet: {data.hex()}")
                    break
                io_id = struct.unpack('>H', data[offset:offset+2])[0]
                offset += 2
                io_value = struct.unpack('>Q', data[offset:offset+8])[0]
                offset += 8
                record['io_data'].append({'io_id': io_id, 'io_value': io_value})

            io_count_xb = struct.unpack('>H', data[offset:offset+2])[0]
            offset += 2
            for _ in range(io_count_xb):
                if offset + 4 > len(data) - 4:
                    logging.error(f"Insufficient data for X-byte IO in record {_+1}, packet: {data.hex()}")
                    break
                io_id = struct.unpack('>H', data[offset:offset+2])[0]
                offset += 2
                io_length = struct.unpack('>H', data[offset:offset+2])[0]
                offset += 2
                if offset + io_length > len(data) - 4:
                    logging.error(f"Insufficient data for X-byte IO value (length {io_length}), packet: {data.hex()}")
                    break
                io_value = int.from_bytes(data[offset:offset+io_length], byteorder='big')
                offset += io_length
                record['io_data'].append({'io_id': io_id, 'io_value': io_value})

            records.append(record)

        # Send data to API
        payload = {'imei': imei, 'records': records}
        logging.info(f"payload: {payload}")
        try:
            response = requests.post(SYNC_DATA_URL, json=payload, timeout=10)
            response.raise_for_status()
            logging.info(f"Sent data to API for IMEI {imei}: {response.json()}")
        except requests.RequestException as e:
            logging.error(f"Failed to send data to API for IMEI {imei}: {e}")

        number_of_data_end = struct.unpack('>H', data[offset:offset+2])[0]
        offset += 2

        if number_of_data != number_of_data_end:
            logging.error(f"Number of data mismatch: Start={number_of_data}, End={number_of_data_end}, packet: {data.hex()}")
            return 0

        return number_of_data
    except Exception as e:
        logging.error(f"Error parsing AVL packet for IMEI {imei}: {e}, packet: {data.hex()}")
        return 0

def main():
    logging.info(f"TCP server v{version} ")
    data=b'\x00\x00\x00\x00\x00\x00\x04\x95\x8e\x12\x00\x00\x01\x95Y\x0f\xba\xf0\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x13\x00\x07\x00\xef\x01\x00\x15\x03\x00\x01\x01\x00qd*4\x00*8\x00*D\x00\x00\x0b\x00B/\x88\x00\x18\x00\x00\x00C\x10\x1d\x00\t\x00+\x00\x19\x7f\xff\x00\x1a\x7f\xff\x00\x1c\x7f\xff\x00V\xff\xff*0\x00\x00*H\x00\x00*X\x00\x00\x00\x01\x00\x10\x00$\xf1\x0b\x00\x00\x00\x00\x00\x00\x01\x95Y\x0f\xd2k\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00*L\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01*L\x00\x01\x01\x00\x00\x01\x95Y\x0f\xd2u\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00*M\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01*M\x00\x01\x01\x00\x00\x01\x95Y\x10\xa5P\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x13\x00\x07\x00\xef\x01\x00\x15\x03\x00\x01\x01\x00qd*4\x00*8\x00*D\x00\x00\x0b\x00B/\x8b\x00\x18\x00\x00\x00C\x10!\x00\t\x00+\x00\x19\x7f\xff\x00\x1a\x7f\xff\x00\x1c\x7f\xff\x00V\xff\xff*0\x00\x00*H\x00\x00*X\x00\x00\x00\x01\x00\x10\x00$\xf1\x0b\x00\x00\x00\x00\x00\x00\x01\x95Y\x10\xbc\xcb\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00*L\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01*L\x00\x01\x01\x00\x00\x01\x95Y\x10\xbc\xd5\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00*M\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01*M\x00\x01\x01\x00\x00\x01\x95Y\x11\x8f\xb0\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x13\x00\x07\x00\xef\x01\x00\x15\x03\x00\x01\x01\x00qd*4\x00*8\x00*D\x00\x00\x0b\x00B/\x88\x00\x18\x00\x00\x00C\x10\x1c\x00\t\x00+\x00\x19\x7f\xff\x00\x1a\x7f\xff\x00\x1c\x7f\xff\x00V\xff\xff*0\x00\x00*H\x00\x00*X\x00\x00\x00\x01\x00\x10\x00$\xf1\x0b\x00\x00\x00\x00\x00\x00\x01\x95Y\x11\xa7+\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00*L\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01*L\x00\x01\x01\x00\x00\x01\x95Y\x11\xa75\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00*M\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01*M\x00\x01\x01\x00\x00\x01\x95Y\x12z\x10\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x13\x00\x07\x00\xef\x01\x00\x15\x04\x00\x01\x01\x00qd*4\x00*8\x00*D\x00\x00\x0b\x00B/(\x00\x18\x00\x00\x00C\x10\x1d\x00\t\x00+\x00\x19\x7f\xff\x00\x1a\x7f\xff\x00\x1c\x7f\xff\x00V\xff\xff*0\x00\x00*H\x00\x00*X\x00\x00\x00\x01\x00\x10\x00$\xf1\x0b\x00\x00\x00\x00\x00\x00\x01\x95Y\x12\x91\x8b\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00*L\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01*L\x00\x01\x01\x00\x00\x01\x95Y\x12\x91\x95\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00*M\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01*M\x00\x01\x01\x00\x00\x01\x95Y\x13dp\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x13\x00\x07\x00\xef\x01\x00\x15\x03\x00\x01\x01\x00qd*4\x00*8\x00*D\x00\x00\x0b\x00B/,\x00\x18\x00\x00\x00C\x10\x1c\x00\t\x00+\x00\x19\x7f\xff\x00\x1a\x7f\xff\x00\x1c\x7f\xff\x00V\xff\xff*0\x00\x00*H\x00\x00*X\x00\x00\x00\x01\x00\x10\x00$\xf1\x0b\x00\x00\x00\x00\x00\x00\x01\x95Y\x13{\xeb\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00*L\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01*L\x00\x01\x01\x00\x00\x01\x95Y\x13{\xf5\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00*M\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01*M\x00\x01\x01\x00\x00\x01\x95Y\x14N\xd0\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x13\x00\x07\x00\xef\x01\x00\x15\x03\x00\x01\x01\x00qd*4\x00*8\x00*D\x00\x00\x0b\x00B/-\x00\x18\x00\x00\x00C\x10\x1d\x00\t\x00+\x00\x19\x7f\xff\x00\x1a\x7f\xff\x00\x1c\x7f\xff\x00V\xff\xff*0\x00\x00*H\x00\x00*X\x00\x00\x00\x01\x00\x10\x00$\xf1\x0b\x00\x00\x00\x00\x00\x00\x01\x95Y\x14fK\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00*L\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01*L\x00\x01\x01\x00\x00\x01\x95Y\x14fU\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00*M\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01*M\x00\x01\x01\x12\x00\x00*\x8c'
    #data = conn.recv(4096)
    if data:
        num_records = parse_avl_packet(data, "350317177312182", None)
    else:
        logging.warning(f"No AVL data received from ")
    """ with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((HOST, PORT))
            s.listen()
            logging.info(f"TCP server v{version} started on {HOST}:{PORT}")
            #s.settimeout(540)  # Run for 540 seconds max
            try:
                
                conn, addr = s.accept()
                logging.info(f"Connected by {addr}")
                try:
                    # Handle IMEI packet
                    data = conn.recv(2)
                    if not data:
                        logging.warning(f"No IMEI data received from {addr}")
                        conn.close()
                        return
                    imei_length = struct.unpack('>H', data)[0]
                    if imei_length < 1 or imei_length > 17:
                        logging.error(f"Invalid IMEI length: {imei_length}, packet: {data.hex()}")
                        conn.close()
                        return
                    imei_data = conn.recv(imei_length)
                    if len(imei_data) != imei_length:
                        logging.error(f"Incomplete IMEI data: expected {imei_length}, got {len(imei_data)}, packet: {imei_data.hex()}")
                        conn.close()
                        return
                    imei = imei_data.decode('ascii', errors='ignore').strip('\0')
                    logging.info(f"IMEI received: {imei}")
                    conn.sendall(b'\x01')
                    logging.debug(f"Sent IMEI acknowledgment to {addr}")

                    # Handle AVL data
                    send_queued_commands(conn, imei)
                    data = conn.recv(4096)
                    if data:
                        num_records = parse_avl_packet(data, imei, conn)
                        if num_records > 0:
                            conn.sendall(struct.pack('>I', num_records))
                            logging.info(f"Sent acknowledgment for {num_records} records to {addr}")
                        else:
                            logging.warning(f"No records parsed or unsupported codec for IMEI {imei}")
                    else:
                        logging.warning(f"No AVL data received from {addr}")
                except Exception as e:
                    logging.error(f"Error handling client {addr}: {e}, packet: {data.hex() if 'data' in locals() else ''}")
                finally:
                    conn.close()
            except Exception as e:
                logging.error(f"Error accepting connection: {e}")
        except Exception as e:
            logging.error(f"TCP server error: {e}")
            raise """

if __name__ == "__main__":
    main()