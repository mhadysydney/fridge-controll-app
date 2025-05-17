import crcmod
import struct

crc16 = crcmod.mkCrcFun(0x18005, initCrc=0x0000, rev=True)

def build_codec12_packet(command):
    zbit,codec,type,qtity="00000000","0C","05","01"
    #codec = "0C", type = "05", qtity = "01"
    command_bytes = command.encode('UTF-8').hex()
    print(f"command_bytes : {command_bytes}")
    command_length = f"{len(command)+2:08x}"
    command_bytes+="0D0A"
    packSize = int((len(command_bytes)+ 16) / 2)
    packSize=f"{packSize:08x}"
    data_field=codec + qtity + type+command_length+command_bytes+qtity
    print("data_field: ",data_field)
    byte_frm_hex=bytes.fromhex(data_field)
   # print(f"command_len : {command_length}. command_len_hex: {len(command):02x}")
    #data_field = struct.pack('>BBBI', 0x0C, 0x01, 0x05, command_length) + command_bytes + struct.pack('>B', 0x01)
    crc = crc16(byte_frm_hex)
    print(f"crc: {crc:08x}")
    packet = zbit+packSize+data_field+f"{crc:08x}"
    #+(zbit+crc)[-8:]
    #struct.pack('>I', 0) + struct.pack('>I', len(data_field)) + data_field + struct.pack('>I', crc)
    return packet

def crc16_ibm(data: bytes) -> int:
    """
    Calculate CRC-16-IBM (poly=0x8005, init=0x0000, refin=True, refout=True, xorout=0x0000).
    Args:
        data: Input bytes to compute CRC over.
    Returns:
        CRC-16-IBM checksum as an integer.
    """
    crc = 0x0000
    poly = 0x8005  # Normal form, will be bit-reversed for reflection

    for byte in data:
        crc ^= byte  # XOR byte into least significant byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001  # 0xA001 is the bit-reversed poly (0x8005)
            else:
                crc >>= 1
        crc &= 0xFFFF  # Ensure 16-bit

    # Reflect output (reverse bits of the final CRC)
    reflected_crc = 0
    for i in range(16):
        reflected_crc |= ((crc >> i) & 1) << (15 - i)
    return reflected_crc

def build_codec12_packet_2(command):
    command_bytes = command.encode('utf-8')
    #byt=command_bytes[:len(command)]
    command_length = len(command_bytes)
    data_field = struct.pack('>BBBI', 0x0C, 0x01, 0x05, command_length)+command_bytes + struct.pack('>BBB',0x0D,0x0A, 0x01)
    crc = crc16_ibm(data_field)
    print(f"crc: {crc:08x}")
    packet = struct.pack('>I', 0) + struct.pack('>I', len(data_field)) + data_field + struct.pack('>I', crc)
    return packet

if __name__ == "__main__":
    packet = build_codec12_packet("getver")
    print(f"packet:{packet}\nfrom commande: getver")