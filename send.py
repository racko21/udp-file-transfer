import socket
import os
import hashlib
import struct
import threading
import sys
import time

PAYLOAD_LENGTH = 1024
PACKET_SIZE = PAYLOAD_LENGTH + 16 + 32
WINDOW_SIZE = 8
ACK_SIZE = 6
TIMEOUT = 5


def send_file(file_path, ip, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(1)

    transmission_id = int.from_bytes(os.urandom(2), "big")
    file_size = os.path.getsize(file_path)
    file_name = os.path.basename(file_path).encode("utf-8")
    max_sequence_number = (
        file_size // PAYLOAD_LENGTH + ((file_size % PAYLOAD_LENGTH) != 0) + 1
    )

    # Send initial packet with file name and max sequence number
    sequence_number = 0
    zero_packet = (
        struct.pack("!HII", transmission_id, sequence_number, max_sequence_number)
        + file_name
    )
    while True:
        sock.sendto(zero_packet, (ip, port))
        try:
            ack, _ = sock.recvfrom(ACK_SIZE)
            ack_transmission_id, ack_sequence_number = struct.unpack("!HI", ack[:6])
            if (
                ack_transmission_id == transmission_id
                and ack_sequence_number == sequence_number
            ):
                print(f"ack: {ack_sequence_number}")
                break
        except socket.timeout:
            continue
    sequence_number += 1

    # Sliding window variables
    base = 1
    lock = threading.Lock()
    locked = threading.Condition(lock)
    packets = {}
    acked = [False] * max_sequence_number

    def send_packets():
        nonlocal sequence_number
        with open(file_path, "rb") as f:
            f.seek((base - 1) * PAYLOAD_LENGTH)
            while base < max_sequence_number:
                with lock:
                    while (
                        sequence_number < base + WINDOW_SIZE
                        and sequence_number < max_sequence_number
                    ):
                        f.seek((sequence_number - 1) * PAYLOAD_LENGTH)
                        data = f.read(PAYLOAD_LENGTH)
                        packet = (
                            struct.pack("!HI", transmission_id, sequence_number) + data
                        )
                        packets[sequence_number] = packet
                        sock.sendto(packet, (ip, port))
                        sequence_number += 1
                with locked:
                    locked.wait(timeout=3)

    def receive_acks():
        nonlocal base
        ack_sequence_number = 0
        while base < max_sequence_number:
            try:
                start = time.time()
                while base < sequence_number and base < max_sequence_number:
                    now = time.time()
                    if now - start > 1:
                        break
                    ack, _ = sock.recvfrom(ACK_SIZE)
                    ack_transmission_id, ack_sequence_number = struct.unpack(
                        "!HI", ack[:6]
                    )
                    if ack_transmission_id == transmission_id:
                        with lock:
                            if not acked[ack_sequence_number]:
                                acked[ack_sequence_number] = True
                                packets.pop(ack_sequence_number)
                                while base < max_sequence_number and acked[base]:
                                    base += 1
            except socket.timeout:
                for seq in range(base, sequence_number):
                    if not acked[seq]:
                        sock.sendto(packets[seq], (ip, port))
            with locked:
                locked.notify_all()

    send_thread = threading.Thread(target=send_packets)
    ack_thread = threading.Thread(target=receive_acks)
    send_thread.start()
    ack_thread.start()
    send_thread.join()
    ack_thread.join()

    # Send final packet with MD5 checksum
    md5_checksum = calculate_md5(file_path)
    final_packet = struct.pack("!HI", transmission_id, sequence_number) + md5_checksum
    while True:
        sock.sendto(final_packet, (ip, port))
        try:
            ack, _ = sock.recvfrom(ACK_SIZE)
            ack_transmission_id, ack_sequence_number = struct.unpack("!HI", ack[:6])
            if (
                ack_transmission_id == transmission_id
                and ack_sequence_number == sequence_number
            ):
                break
        except socket.timeout:
            continue

    sock.close()


def calculate_md5(file_path):
    md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            md5.update(chunk)
    print(md5.hexdigest())
    return md5.digest()


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python sender.py <file name> <ip address> <port>")
        sys.exit(1)

    filename = sys.argv[1]
    ip_address = sys.argv[2]
    port = int(sys.argv[3])
    send_file(filename, ip_address, port)
