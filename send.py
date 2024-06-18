import socket
import os
import hashlib
import struct
import threading
import sys

PAYLOAD_LENGTH = 1024
PACKET_SIZE = PAYLOAD_LENGTH + 16 + 32
WINDOW_SIZE = 8
ACK_SIZE = 4
TIMEOUT = 100


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
            ack, _ = sock.recvfrom(PACKET_SIZE)
            ack_transmission_id, ack_sequence_number = struct.unpack("!HI", ack[:6])
            if (
                ack_transmission_id == transmission_id
                and ack_sequence_number == sequence_number
            ):
                break
        except socket.timeout:
            continue
    sequence_number += 1

    # Sliding window variables
    base = 1
    lock = threading.Lock()
    locked = threading.Condition(lock)

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
                        sock.sendto(packet, (ip, port))
                        print(f"sequence_number: {sequence_number}")
                        sequence_number += 1

                with locked:
                    locked.wait(timeout=1)

    def receive_acks():
        nonlocal base
        while base < max_sequence_number:
            try:
                ack, _ = sock.recvfrom(PACKET_SIZE)
                ack_transmission_id, ack_sequence_number = struct.unpack("!HI", ack[:6])
                if ack_transmission_id == transmission_id:
                    with lock:
                        base = ack_sequence_number + 1
                    with locked:
                        locked.notify_all()
            except socket.timeout:
                print("timeout")
                continue

    send_thread = threading.Thread(target=send_packets)
    ack_thread = threading.Thread(target=receive_acks)
    send_thread.start()
    ack_thread.start()
    send_thread.join()
    ack_thread.join()

    print(f"max_sequence_number: {max_sequence_number}")
    print(f"last sequence_number: {sequence_number}")

    # Send final packet with MD5 checksum
    md5_checksum = calculate_md5(file_path)
    final_packet = struct.pack("!HI", transmission_id, sequence_number) + md5_checksum
    while True:
        sock.sendto(final_packet, (ip, port))
        try:
            ack, _ = sock.recvfrom(PACKET_SIZE)
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
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.digest()


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python sender.py <file name> <ip address> <port>")
        sys.exit(1)

    filename = sys.argv[1]
    ip_address = sys.argv[2]
    port = int(sys.argv[3])
    send_file(filename, ip_address, port)

# def send_file(file_path, ip, port):
#     sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
#     sock.settimeout(1)
#
#     file_name = os.path.basename(file_path)
#     file_size = os.path.getsize(file_path)
#     sequence_number = 0
#     window = []
#     max_sequence_number = (
#         file_size // PAYLOAD_LENGTH + ((file_size % PAYLOAD_LENGTH) != 0) + 1
#     )
#
#     # Send file information
#     while True:
#         zero_packet = (
#             struct.pack("!HII", transmission_id, 0, max_sequence_number) + file_name.encode()
#         )
#         sock.sendto(zero_packet, (ip, port))
#         try:
#             ack_packet, addr = sock.recvfrom(ACK_SIZE)
#             ack = struct.unpack("!I", ack_packet)[0]
#             if ack == 1:
#                 break
#         except socket.timeout:
#             continue
#
#     sequence_number += 1
#
#     # Sending the file data
#     with open(file_path, "rb") as file:
#         md5_hash = hashlib.md5()
#         while True:
#             while sequence_number - ack < WINDOW_SIZE:
#                 data = file.read(PAYLOAD_LENGTH)
#                 if not data:
#                     break
#                 md5_hash.update(data)
#                 data_packet = struct.pack("!HI", transmission_id, sequence_number) + data
#                 sock.sendto(data_packet, (ip, port))
#                 window[sequence_number] = data_packet
#                 sequence_number += 1
#             while ack != sequence_number:
#                 ack_packet, _ = sock.recvfrom(ACK_SIZE)
#                 ack, n_ack = struct.unpack("!Ic", ack_packet)
#                 if n_ack == "1":
#                     sock.sendto(window[ack], (ip, port))
#                 else:
#                     for i in range(ack - WINDOW_SIZE, ack):
#                         window.pop(i)
#                     if ack == max_sequence_number:
#                         break
#             else:
#                 continue
#             break
#
#     # Sending the checksum
#     while True:
#         md5_packet = struct.pack(">HI", transmission_id, sequence_number) + md5_hash.digest()
#         sock.sendto(md5_packet, (ip, port))
#         try:
#             ack_packet, _ = sock.recvfrom(ACK_SIZE)
#             ack = struct.unpack("!I", ack_packet)[0]
#             if ack == max_sequence_number:
#                 break
#         except socket.timeout:
#             continue
#
#     sock.close()
#
#
# def send_zero_packet(
#     sock, ip, port, window, transmission_id, max_sequence_number, file_name
# ):
#     zero_packet = (
#         struct.pack("!HII", transmission_id, 0, max_sequence_number) + file_name.encode()
#     )
#     sock.sendto(zero_packet, (ip, port))
#     window.append(0)


# import socket
# import struct
# import hashlib
# import os
# import threading
#
# WINDOW_SIZE = 5  # Größe des Sliding Windows
#
# def calculate_md5(file_path):
#     hash_md5 = hashlib.md5()
#     with open(file_path, "rb") as f:
#         for chunk in iter(lambda: f.read(4096), b""):
#             hash_md5.update(chunk)
#     return hash_md5.hexdigest()
#
##
# if __name__ == "__main__":
#     file_path = 'path/to/your/file.txt'
#     server_address = 'localhost'
#     server_port = 5005
#     send_file(file_path, server_address, server_port)
#
