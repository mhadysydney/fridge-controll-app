import logging
import socket
import struct
from datetime import datetime, timezone
import os
import sys
import requests
import time
import crcmod

LOG_FILE = 'tcp_server.log'
API_URL = 'https://iot.satgroupe.com'  # Adjust to your cPanel subdomain or IP
COMMAND_QUEUE_URL = f'{API_URL}/command_queue'
SYNC_DATA_URL = f'{API_URL}/syncing_data'

try:
    log_dir = os.path.dirname(LOG_FILE)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, mode=0o755)
    logging.basicConfig(
        filename=LOG_FILE,
        level=logging.DEBUG,
        format='%(asctime)s:%(levelname)s:%(message)s'
    )
    logging.info("TCP server logging initialized")
except Exception as e:
    logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)
    logging.error(f"Failed to initialize TCP server logging: {e}")

# CRC-16 (IBM) for FMB920
crc16 = crcmod.mkCrcFun(0x18005, initCrc=0xFFFF, rev=True, xorOut=0x0000)

def calculate_crc(data):
    return crc16(data)

def verify_crc(data, expected_crc):
    calculated_crc = calculate_crc(data[:-2])
    return calculated_crc == expected_crc

def build_codec12_packet(command):
    command_bytes = command.encode('ascii')
    command_length = len(command_bytes)
    data_field = struct.pack('>BBBI', 0x0C, 0x01, 0x05, command_length) + command_bytes + struct.pack('>B', 0x01)
    crc = crc16(data_field)
    packet = struct.pack('>I', 0) + struct.pack('>I', len(data_field)) + data_field + struct.pack('>I', crc)
    return packet

def parse_timestamp(data, offset, length=8):
    try:
        if len(data[offset:offset+length]) != length:
            logging.error(f"Insufficient data for timestamp at offset {offset}, packet: {data.hex()}")
            return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        timestamp_ms = int.from_bytes(data[offset:offset+length], byteorder='big')
        timestamp_s = timestamp_ms / 1000.0
        epoch_start = 0
        epoch_end = 2147483647
        if timestamp_s < epoch_start or timestamp_s > epoch_end:
            logging.error(f"Invalid timestamp_ms: {timestamp_ms}, packet: {data.hex()}")
            return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        timestamp = datetime.fromtimestamp(timestamp_s, tz=timezone.utc)
        return timestamp.strftime('%Y-%m-%d %H:%M:%S')
    except Exception as e:
        logging.error(f"Failed to parse timestamp at offset {offset}: {e}, packet: {data.hex()}")
        return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

def parse_codec12_response(data):
    try:
        if len(data) < 10:
            logging.error(f"Codec 12 response too short: {len(data)} bytes, packet: {data.hex()}")
            return None

        offset = 0
        data_length = int.from_bytes(data[offset:offset+4], byteorder='big')
        offset += 4
        codec_id = data[offset]
        if codec_id != 0x0C:
            logging.error(f"Invalid Codec ID: {codec_id}, expected 0x0C, packet: {data.hex()}")
            return None
        offset += 1
        response_type = data[offset]
        offset += 1
        response_size = data[offset]
        offset += 1
        response_data = data[offset:offset+response_size].decode('ascii', errors='ignore')
        offset += response_size
        number_of_data = data[offset]
        offset += 1
        crc = int.from_bytes(data[offset:offset+2], byteorder='big')
        if not verify_crc(data[4:offset], crc):
            logging.error(f"CRC check failed for Codec 12 response, packet: {data.hex()}")
            return None

        logging.info(f"Parsed Codec 12 response: type={response_type}, data='{response_data}'")
        return {'type': response_type, 'data': response_data}
    except Exception as e:
        logging.error(f"Failed to parse Codec 12 response: {e}, packet: {data.hex()}")
        return None

def send_command_with_response(conn, command, imei):
    try:
        packet = build_codec12_packet(command)
        conn.sendall(packet)
        logging.info(f"Sent Codec 12 command to IMEI {imei}: {command}")
        conn.settimeout(5)
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

def send_queued_commands(client_socket, imei):
    try:
        response = requests.get(f"{COMMAND_QUEUE_URL}/{imei}", timeout=10)
        response.raise_for_status()
        commands = response.json().get('commands', [])
        logging.debug(f"Fetched {len(commands)} pending commands for IMEI {imei}")

        for command_entry in commands:
            command_id = command_entry['id']
            command = command_entry['command']
            response = send_command_with_response(client_socket, command, imei)
            if response:
                try:
                    requests.post(f"{COMMAND_QUEUE_URL}/update/{command_id}", json={'status': 'completed'}, timeout=10)
                    logging.info(f"Command {command_id} ('{command}') marked as completed for IMEI {imei}")
                except requests.RequestException as e:
                    logging.error(f"Failed to update command {command_id} status: {e}")
            else:
                logging.error(f"Command {command_id} ('{command}') failed for IMEI {imei}")
    except requests.RequestException as e:
        logging.error(f"Failed to fetch queued commands for IMEI {imei}: {e}")

def handle_client(client_socket, address):
    try:
        data = client_socket.recv(1024)
        if not data:
            logging.info(f"No data received from {address}")
            return
        logging.debug(f"Received data from {address}: {data.hex()}")

        imei_length = int.from_bytes(data[0:2], byteorder='big')
        imei = data[2:2+imei_length].decode('ascii', errors='ignore')
        
        logging.info(f"Received IMEI packet: {imei}. imei_length {imei_length} from {address}")
        client_socket.sendall(b'\x01')  # Acknowledge IMEI
        logging.debug(f"Sent IMEI acknowledgment to {address}")
            
        data = client_socket.recv(4096)
        # Handle Codec 8E packet
        offset = 0
        if not data:
            logging.error(f"Inavalid data recieved after IMEI: {len(data)} bytes, packet: {data.hex()}")
            return 

        data_length = int.from_bytes(data[0:4], byteorder='big')
        offset = 4
        """crc = int.from_bytes(data[-2:], byteorder='big')
         if not verify_crc(data[4:-2], crc):
            logging.error(f"CRC check failed, packet: {data.hex()}")
            return
 """
        #imei_length = int.from_bytes(data[offset:offset+2], byteorder='big')
        offset += 2
        #imei = data[offset:offset+imei_length].decode('ascii', errors='ignore')
        offset += imei_length

        codec_id = data[offset]
        if codec_id != 0x8E:
            logging.error(f"Unsupported codec ID: {codec_id}, expected 0x8E, packet: {data.hex()}")
            return
        offset += 1

        number_of_data = data[offset]
        offset += 1

        logging.info(f"Processing data for IMEI {imei}, Codec ID {codec_id}, Records {number_of_data}")

        records = []
        for i in range(number_of_data):
            if offset + 8 > len(data) - 2:
                logging.error(f"Insufficient data for timestamp in record {i+1}, packet: {data.hex()}")
                break

            timestamp = parse_timestamp(data, offset)
            offset += 8

            if offset + 16 > len(data) - 2:
                logging.error(f"Insufficient data for GPS in record {i+1}, packet: {data.hex()}")
                break

            priority = data[offset]
            offset += 1
            longitude = struct.unpack('>i', data[offset:offset+4])[0] / 10000000.0
            offset += 4
            latitude = struct.unpack('>i', data[offset:offset+4])[0] / 10000000.0
            offset += 4
            altitude = struct.unpack('>h', data[offset:offset+2])[0]
            offset += 2
            angle = struct.unpack('>h', data[offset:offset+2])[0]
            offset += 2
            satellites = data[offset]
            offset += 1
            speed = struct.unpack('>h', data[offset:offset+2])[0]
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

            if offset + 5 > len(data) - 2:
                logging.error(f"Insufficient data for IO in record {i+1}, packet: {data.hex()}")
                break

            event_id = data[offset]
            offset += 1
            n_total_io = data[offset]
            offset += 1

            for _ in range(n_total_io):
                if offset + 2 > len(data) - 2:
                    logging.error(f"Insufficient data for IO element in record {i+1}, packet: {data.hex()}")
                    break
                io_id = data[offset]
                offset += 1
                value_length = data[offset]
                offset += 1

                if value_length not in [1, 2, 4, 8]:
                    logging.error(f"Invalid IO value length {value_length} for io_id {io_id}, packet: {data.hex()}")
                    continue
                if offset + value_length > len(data) - 2:
                    logging.error(f"Insufficient data for IO value (length {value_length}), packet: {data.hex()}")
                    break

                if value_length == 1:
                    io_value = data[offset]
                elif value_length == 2:
                    io_value = struct.unpack('>h', data[offset:offset+value_length])[0]
                elif value_length == 4:
                    io_value = struct.unpack('>i', data[offset:offset+value_length])[0]
                else:
                    io_value = struct.unpack('>q', data[offset:offset+value_length])[0]
                offset += value_length

                record['io_data'].append({'io_id': io_id, 'io_value': io_value})

            records.append(record)

        # Send data to API
        payload = {'imei': imei, 'records': records}
        try:
            response = requests.post(SYNC_DATA_URL, json=payload, timeout=10)
            response.raise_for_status()
            logging.info(f"Sent data to API for IMEI {imei}: {response.json()}")
        except requests.RequestException as e:
            logging.error(f"Failed to send data to API for IMEI {imei}: {e}")

        # Send queued commands
        send_queued_commands(client_socket, imei)

        # Send acknowledgment
        ack = struct.pack('>I', number_of_data)
        client_socket.sendall(ack)
        logging.info(f"Sent acknowledgment for {number_of_data} records to {address}")

    except Exception as e:
        logging.error(f"Error handling client {address}: {e}, packet: {data.hex()}")
    finally:
        client_socket.close()

def main():
    try:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(('0.0.0.0', 50120))
        server.listen(5)
        logging.info("TCP server started on port 50120")
        while True:
            client_socket, address = server.accept()
            logging.info(f"Accepted connection from {address}")
            handle_client(client_socket, address)
    except Exception as e:
        logging.error(f"Server error: {e}")
        raise

if __name__ == '__main__':
    main()