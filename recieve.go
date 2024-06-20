package main

import (
	"bytes"
	"crypto/md5"
	"encoding/binary"
	"fmt"
	"io"
	"net"
	"os"
	"strconv"
	"time"
)

const (
	PAYLOAD_LENGTH = 1024
	PACKET_SIZE    = PAYLOAD_LENGTH + 6
	TIMEOUT        = 100 * time.Millisecond
)

func receiveFile(port int) {
	// addr, err := net.ResolveUDPAddr("udp", fmt.Sprintf(":%d", port))
	// if err != nil {
	// 	panic(err)
	// }
	addr := net.UDPAddr{
		IP:   net.ParseIP("0.0.0.0"),
		Port: port,
	}
	conn, err := net.ListenUDP("udp", &addr)
	if err != nil {
		fmt.Printf("Listen err %v", err)
	}
	defer conn.Close()

	buffer := make([]byte, PACKET_SIZE)
	var transmissionID uint16
	var sequenceNumber, maxSequenceNumber uint32
	var fileName string
	var TRANSMISSIONID uint16
	receivedData := make(map[uint32][]byte)

	fmt.Printf("Listening on port %d...\n", port)
	fmt.Println()

	conn.SetReadDeadline(time.Now().Add(10 * time.Second))
	for {
		n, raddr, err := conn.ReadFromUDP(buffer)
		if err != nil {
			fmt.Println("Timeout: file information not received")
			return
		}
		if sequenceNumber == 0 {
			TRANSMISSIONID = binary.BigEndian.Uint16(buffer[0:2])
			sequenceNumber = binary.BigEndian.Uint32(buffer[2:6])
			maxSequenceNumber = binary.BigEndian.Uint32(buffer[6:10])
			fileName = string(buffer[10:n])
			fmt.Printf("Receiving file: %s\n", fileName)
			fmt.Println()
			// fmt.Printf("sequenceNumber: %v\n", sequenceNumber)
			ackPacket := make([]byte, 6)
			binary.BigEndian.PutUint16(ackPacket[0:2], transmissionID)
			binary.BigEndian.PutUint32(ackPacket[2:6], sequenceNumber)
			conn.WriteToUDP(ackPacket, raddr)
			break
		}
	}

	var fileMd5 []byte
	conn.SetReadDeadline(time.Now().Add(TIMEOUT))
	for {
		n, raddr, err := conn.ReadFromUDP(buffer)
		if err != nil {
			if netErr, ok := err.(net.Error); ok && netErr.Timeout() {
				conn.SetReadDeadline(time.Now().Add(TIMEOUT))
				continue
			}
		}
		transmissionID = binary.BigEndian.Uint16(buffer[0:2])
		sequenceNumber = binary.BigEndian.Uint32(buffer[2:6])
		// fmt.Printf("sequenceNumber: %v\n", sequenceNumber)

		if transmissionID != TRANSMISSIONID {
			continue
		}

		if sequenceNumber == maxSequenceNumber {
			fileMd5 = buffer[6:n]
			ackPacket := make([]byte, 6)
			binary.BigEndian.PutUint16(ackPacket[0:2], transmissionID)
			binary.BigEndian.PutUint32(ackPacket[2:6], sequenceNumber)
			conn.WriteToUDP(ackPacket, raddr)
			break
		} else {
			receivedData[sequenceNumber] = make([]byte, n-6)
			copy(receivedData[sequenceNumber], buffer[6:n])
			ackPacket := make([]byte, 6)
			binary.BigEndian.PutUint16(ackPacket[0:2], transmissionID)
			binary.BigEndian.PutUint32(ackPacket[2:6], sequenceNumber)
			conn.WriteToUDP(ackPacket, raddr)
		}
	}

	file, err := os.Create(fileName)
	if err != nil {
		panic(err)
	}
	defer file.Close()

	for i := uint32(1); i < maxSequenceNumber; i++ {
		file.Write(receivedData[i])
	}

	println("File received, verifying integrity...")

	verifyFileIntegrity(fileName, fileMd5)
}

func verifyFileIntegrity(filePath string, originalMd5 []byte) {
	file, err := os.Open(filePath)
	if err != nil {
		panic(err)
	}
	defer file.Close()

	hash := md5.New()
	if _, err := io.Copy(hash, file); err != nil {
		panic(err)
	}
	md5 := hash.Sum(nil)

	if bytes.Equal(md5, originalMd5) {
		fmt.Println("File integrity verified successfully.")
	} else {
		fmt.Println("File integrity verification failed.")
	}
}

func main() {
	if len(os.Args) != 2 {
		fmt.Println("Usage: go run receive.go <port>")
		os.Exit(1)
	}

	port, err := strconv.Atoi(os.Args[1])
	if err != nil {
		fmt.Println("Invalid port number")
		os.Exit(1)
	}
	receiveFile(port)
}
