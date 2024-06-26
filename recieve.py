import socket
import struct
import hashlib
import sys

PAYLOAD_LENGTH = 1024
PACKET_SIZE = PAYLOAD_LENGTH + 16 + 32


def receive_file(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", port))

    received_data = {}
    sequence_number = 0
    max_sequence_number = float("inf")
    packet_count = 0
    TRANSMISSION_ID = None
    file_name = ""

    print(f"Listening on port {port}...")

    while True:
        packet, addr = sock.recvfrom(PACKET_SIZE)
        transmission_id, sequence_number = struct.unpack("!HI", packet[:6])

        if transmission_id is None:
            TRANSMISSION_ID = transmission_id
        elif transmission_id != TRANSMISSION_ID:
            continue

        if sequence_number == 0:
            max_sequence_number = struct.unpack("!I", packet[6:10])[0]
            file_name = packet[10:].decode("utf-8")
            sock.sendto(struct.pack("!HI", transmission_id, sequence_number), addr)
        elif sequence_number == max_sequence_number:
            file_md5 = packet[6:]
            sock.sendto(struct.pack("!HI", transmission_id, sequence_number), addr)
            break
        else:
            if sequence_number not in received_data:
                received_data[sequence_number] = packet[6:]
                packet_count += 1
            sock.sendto(struct.pack("!HI", transmission_id, sequence_number), addr)
            print(f"sequence_number: {sequence_number}")

    # Reconstruct the file
    if file_name == "":
        print("Error reconstructing file name")
        exit()
    with open(file_name, "wb") as f:
        for i in sorted(received_data.keys()):
            f.write(received_data[i])

    print("File has been reconstructed. Verifying integrity...")
    verify_file_integrity(file_name, file_md5)
    sock.close()


def verify_file_integrity(file_path, original_md5):
    md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            md5.update(chunk)

    if md5.digest() == original_md5:
        print("File integrity verified successfully.")
    else:
        print("File integrity verification failed.")
        print(md5.hexdigest())


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python receiver.py <port>")
        sys.exit(1)

    # ip = sys.argv[1]
    port = int(sys.argv[1])
    receive_file(port)
