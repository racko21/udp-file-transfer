import socket
import os
import hashlib
from struct import pack
import sys

payload_length = 1024

def send_file(file_path, ip, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    file_name = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    transmission_id = int.from_bytes(os.urandom(2), 'big')
    max_sequence_number = file_size // payload_length + ((file_size % payload_length) != 0 ) + 1
    sequence_number = 0
    print("max sequence_number:", max_sequence_number)

    # Send file information
    zero_packet = pack('!HII', transmission_id, sequence_number, max_sequence_number) + file_name.encode()
    sock.sendto(zero_packet, (ip, port))
    sequence_number += 1

    # Sending the file data
    with open(file_path, 'rb') as file:
        md5_hash = hashlib.md5()
        while True:
            data = file.read(payload_length)
            if not data:
                break
            md5_hash.update(data)
            data_packet = pack('!HI', transmission_id, sequence_number) + data
            sock.sendto(data_packet, (ip, port))
            print(sequence_number)
            sequence_number += 1

    # Sending the MD5 hash
    md5_packet = pack('>HI', transmission_id, sequence_number) + md5_hash.digest()
    print(sequence_number)
    print("MD5:",md5_hash)
    sock.sendto(md5_packet, (ip, port))
    sock.close()

if __name__ == '__main__':
    if len(sys.argv) != 4:
        print("Usage: python sender.py <file name> <ip address> <port>")
        sys.exit(1)

    filename = sys.argv[1]
    ip_address = sys.argv[2]
    port = int(sys.argv[3])
    send_file(filename, ip_address, port)
