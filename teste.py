import crcmod
import struct

crc16 = crcmod.mkCrcFun(0x18005, initCrc=0x0000, rev=True)

def build_codec12_packet(command):
    zbit,codec,type,qtity="00000000","0C","05","01"
    #codec = "0C", type = "05", qtity = "01"
    command_bytes = command.encode('UTF-8')
    #print(f"command_bytes : {command_bytes}")
    command_length = len(command)
    #command_bytes+="0D0A"
    packSize = int((len(command_bytes)+ 16) / 2)
    packSize=f"{packSize:08x}"
    data_field=codec + qtity + type+f"{command_length:08x}"+command_bytes.hex()+qtity
    #print("data_field: ",data_field)
    byte_frm_hex=bytes.fromhex(data_field)
   # print(f"command_len : {command_length}. command_len_hex: {len(command):02x}")
    data_field = struct.pack('>BBBI', 0x0C, 0x01, 0x05, command_length) + command_bytes + struct.pack('>B', 0x01)
    crc = crc16(data_field)
    print(f"crc: {crc:08x}")
     #= zbit+packSize+data_field+f"{crc:08x}"
    #+(zbit+crc)[-8:]
    packet=struct.pack('>I', 0) + struct.pack('>I', len(data_field)) + data_field + struct.pack('>I', crc)
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
    command_length = len(command_bytes)
    data_field = struct.pack('>BBBI', 0x0C, 0x01, 0x05, command_length)+command_bytes + struct.pack('>B', 0x01)
    crc = crc16(data_field)
    print(f"crc: {crc:08x}")
    packet = struct.pack('>I', 0) + struct.pack('>I', len(data_field)) + data_field + struct.pack('>I', crc)
    return packet

def parse_codec12_packet(packet):
    byte_from_hex=bytes.fromhex(packet)
    print("unpacked_msg1:",byte_from_hex[16:-5].decode("utf-8"))
    unpack=byte_from_hex[16:-5].decode("utf-8")
    return unpack

def build_codec12_packet_3(command):
    command_bytes = command.encode('ascii')
    command_length = len(command_bytes)
    data_field = struct.pack('>BBBI', 0x0C, 0x01, 0x05, command_length) + command_bytes + struct.pack('>B', 0x01)
    crc = crc16(data_field)
    packet = struct.pack('>I', 0) + struct.pack('>I', len(data_field)) + data_field + struct.pack('>I', crc)
    return packet

if __name__ == "__main__":
    cmd="setdigout 1 4000\r\n"
    responsePacket="00000000000000900C010600000088494E493A323031392F372F323220373A3232205254433A323031392F372F323220373A3533205253543A32204552523A 312053523A302042523A302043463A302046473A3020464C3A302054553A302F302055543A3020534D533A30204E4F4750533A303A3330204750533A312053 41543A302052533A332052463A36352053463A31204D443A30010000C78F"
    packet = build_codec12_packet_3(cmd)
    print(f"packet:{packet}\nfrom commande: {cmd}")
    print("unpacked msg2: ",parse_codec12_packet(responsePacket))