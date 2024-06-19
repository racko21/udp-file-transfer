package main

import (
	"crypto/md5"
	"encoding/binary"
	"fmt"
	"io"
	"math/rand"
	"net"
	"os"
	"strconv"
	"sync"
	"time"
)

const (
	PAYLOAD_LENGTH = 1024
	PACKET_SIZE    = PAYLOAD_LENGTH + 6
	WINDOW_SIZE    = 8
	ACK_SIZE       = 6
	TIMEOUT        = 100 * time.Millisecond
)

func sendFile(filePath, ip string, port int) {
	// addr, err := net.ResolveUDPAddr("udp", fmt.Sprintf("%s:%d", ip, port))
	// if err != nil {
	// 	panic(err)
	// }
	addr := fmt.Sprintf("%s:%d", ip, port)
	conn, err := net.Dial("udp", addr)
	if err != nil {
		panic(err)
	}
	defer conn.Close()
	transmissionID := uint16(rand.Uint32() % 65535)
	fileInfo, err := os.Stat(filePath)
	if err != nil {
		panic(err)
	}
	fileSize := fileInfo.Size()
	sequenceNumber := uint32(0)
	maxSequenceNumber := uint32(fileSize / PAYLOAD_LENGTH)
	if fileSize%PAYLOAD_LENGTH == 0 {
		maxSequenceNumber += 1
	} else {
		maxSequenceNumber += 2
	}

	zeroPacket := make([]byte, 10+len(filePath))
	binary.BigEndian.PutUint16(zeroPacket[0:2], transmissionID)
	binary.BigEndian.PutUint32(zeroPacket[2:6], sequenceNumber)
	binary.BigEndian.PutUint32(zeroPacket[6:10], maxSequenceNumber)
	copy(zeroPacket[10:], []byte(filePath))

	for {
		conn.Write(zeroPacket)
		ack := make([]byte, ACK_SIZE)
		conn.SetReadDeadline(time.Now().Add(TIMEOUT))
		_, err := conn.Read(ack)
		if err == nil {
			ackTransmissionID := binary.BigEndian.Uint16(ack[0:2])
			ackSequenceNumber := binary.BigEndian.Uint32(ack[2:6])
			if ackTransmissionID == transmissionID && ackSequenceNumber == sequenceNumber {
				fmt.Printf("Ack: %d\n", ackSequenceNumber)
				break
			}
		}
	}
	sequenceNumber++

	var lock sync.Mutex
	base := uint32(1)
	acked := make([]bool, maxSequenceNumber)
	packets := make(map[uint32][]byte)
	var wg sync.WaitGroup

	sendPackets := func() {
		defer wg.Done()
		file, err := os.Open(filePath)
		if err != nil {
			panic(err)
		}
		defer file.Close()

		for base < maxSequenceNumber {
			lock.Lock()
			for sequenceNumber < base+WINDOW_SIZE && sequenceNumber < maxSequenceNumber {
				data := make([]byte, PAYLOAD_LENGTH)
				file.Seek(int64((sequenceNumber-1)*PAYLOAD_LENGTH), io.SeekStart)
				n, err := file.Read(data)
				if err != nil && err != io.EOF {
					panic(err)
				}
				if n == 0 {
					break
				}
				packet := make([]byte, 6+n)
				binary.BigEndian.PutUint16(packet[0:2], transmissionID)
				binary.BigEndian.PutUint32(packet[2:6], sequenceNumber)
				copy(packet[6:], data[:])
				packets[sequenceNumber] = packet
				conn.Write(packet)
				fmt.Printf("Sent: %d\n", sequenceNumber)
				sequenceNumber++
			}
			lock.Unlock()
			time.Sleep(TIMEOUT)
		}
	}

	receiveAcks := func() {
		defer wg.Done()
		ack := make([]byte, ACK_SIZE)
		for base < maxSequenceNumber {
			conn.SetReadDeadline(time.Now().Add(TIMEOUT))
			_, err := conn.Read(ack)
			if err == nil {
				ackTransmissionID := binary.BigEndian.Uint16(ack[0:2])
				ackSequenceNumber := binary.BigEndian.Uint32(ack[2:6])
				fmt.Printf("Ack: %d\n", ackSequenceNumber)
				if ackTransmissionID == transmissionID {
					lock.Lock()
					if !acked[ackSequenceNumber] {
						acked[ackSequenceNumber] = true
						delete(packets, ackSequenceNumber)
						for base < maxSequenceNumber && acked[base] {
							base++
						}
					}
					lock.Unlock()
				}
			} else {
				lock.Lock()
				for seq := base; seq < sequenceNumber; seq++ {
					if !acked[seq] {
						conn.Write(packets[seq])
						fmt.Printf("Resent: %d\n", seq)
					}
				}
				lock.Unlock()
			}
		}
	}

	wg.Add(2)
	go sendPackets()
	go receiveAcks()
	wg.Wait()

	fileMd5 := calculateMD5(filePath)
	finalPacket := make([]byte, 6+len(fileMd5))
	binary.BigEndian.PutUint16(finalPacket[0:2], transmissionID)
	binary.BigEndian.PutUint32(finalPacket[2:6], sequenceNumber)
	copy(finalPacket[6:], fileMd5)
	for {
		conn.Write(finalPacket)
		fmt.Printf("Sent final packet: %d\n", sequenceNumber)
		ack := make([]byte, ACK_SIZE)
		conn.SetReadDeadline(time.Now().Add(TIMEOUT))
		_, err := conn.Read(ack)
		if err == nil {
			ackTransmissionID := binary.BigEndian.Uint16(ack[0:2])
			ackSequenceNumber := binary.BigEndian.Uint32(ack[2:6])
			if ackTransmissionID == transmissionID && ackSequenceNumber == sequenceNumber {
				fmt.Printf("Received final ack: %d\n", ackSequenceNumber)
				break
			}
		}
	}
}

func calculateMD5(filePath string) []byte {
	file, err := os.Open(filePath)
	if err != nil {
		panic(err)
	}
	defer file.Close()

	hash := md5.New()
	if _, err := io.Copy(hash, file); err != nil {
		panic(err)
	}
	return hash.Sum(nil)
}

func main() {
	if len(os.Args) != 4 {
		fmt.Println("Usage: go run send.go <file name> <ip address> <port>")
		os.Exit(1)
	}

	filePath := os.Args[1]
	ip := os.Args[2]
	port, err := strconv.Atoi(os.Args[3])
	if err != nil {
		fmt.Println("Invalid port number")
		os.Exit(1)
	}
	sendFile(filePath, ip, port)
}
