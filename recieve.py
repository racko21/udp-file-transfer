import socket
from struct import unpack
import hashlib
import sys

payload_length = 1024
packet_size = payload_length + 16 + 32

def receive_file(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('', port))

    file_name = ""
    max_sequence_number = float('inf')
    packet_count = 0
    received_data = {}
    TRANSMISSION_ID = None

    print(f"Listening on port {port}...")

    while packet_count < max_sequence_number+1:
        packet, addr = sock.recvfrom(packet_size)
        transmission_id, sequence_number = unpack('!HI', packet[:6])
        print("s_num:",sequence_number)
        print("p_count:",packet_count)

        if TRANSMISSION_ID is None:
            TRANSMISSION_ID = transmission_id

        if transmission_id == TRANSMISSION_ID:
            if sequence_number == max_sequence_number:
                file_md5 = packet[6:]
                print("MD5:",file_md5)
                packet_count += 1
            elif sequence_number == 0:
                max_sequence_number = unpack('!I', packet[6:10])[0]
                print("max_sequence_number",max_sequence_number)
                file_name = packet[10:].decode().strip()
                print(f"Receiving file: {file_name}")
                packet_count += 1
            else:
                received_data[sequence_number] = packet[6:]
                packet_count += 1

    # Reconstruct the file
    if file_name == "":
        print("Error reconstructing file name")
        exit()
    with open(file_name, 'wb') as f:
        for i in sorted(received_data.keys()):
            f.write(received_data[i])

    print("File has been reconstructed. Verifying integrity...")
    verify_file_integrity(file_name, file_md5)
    sock.close()

def verify_file_integrity(file_path, original_md5):
    md5 = hashlib.md5()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            md5.update(chunk)

    print("original MD5:", original_md5)
    if md5.digest() == original_md5:
        print("File integrity verified successfully.")
    else:
        print("File integrity verification failed.")

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: python receiver.py <port>")
        sys.exit(1)

    port = int(sys.argv[1])
    receive_file(port)
