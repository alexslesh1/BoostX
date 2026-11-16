// nexora-testrelay is a relay with a fake internet behind it, for checking
// the engine on a Windows machine without any server. It runs anywhere.
//
//	nexora-testrelay -listen 127.0.0.1:4799 -out session.json
//
// It writes the relay's public key and a valid token to session.json, then
// serves. Behind it, every address on the internet answers:
//   - a UDP datagram comes straight back with "echo:" in front of it;
//   - a TCP connection attempt is refused (RST).
//
// So when a routed program sends UDP to an address that does not exist
// (say 1.2.3.4) and gets an echo back, its packets really went through the
// engine, the tunnel and back. Unrouted programs get no answer at all.
package main

import (
	"bytes"
	"encoding/base64"
	"encoding/binary"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log"
	"net"
	"net/netip"
	"os"
	"os/signal"
	"sync"
	"time"

	"nexora.app/core/packet"
	"nexora.app/core/proto"
	"nexora.app/core/relay"
)

// fakeInternet stands in for the relay's TUN device and the internet
// behind it.
type fakeInternet struct {
	replies chan []byte
	closed  chan struct{}
	once    sync.Once
	mu      sync.Mutex
	seen    int
}

func (f *fakeInternet) Write(p []byte) (int, error) {
	if reply := answer(p); reply != nil {
		f.mu.Lock()
		f.seen++
		f.mu.Unlock()
		select {
		case f.replies <- reply:
		default:
		}
	}
	return len(p), nil
}

func (f *fakeInternet) Read(p []byte) (int, error) {
	select {
	case reply := <-f.replies:
		return copy(p, reply), nil
	case <-f.closed:
		return 0, io.EOF
	}
}

func (f *fakeInternet) Close() error {
	f.once.Do(func() { close(f.closed) })
	return nil
}

// answer builds the reply the "internet" sends for one packet, or nil.
func answer(p []byte) []byte {
	info, err := packet.Parse(p)
	if err != nil || !info.FirstFragment || info.Fragmented {
		return nil
	}
	l4 := info.L4Offset
	switch info.Proto {
	case packet.ProtoUDP:
		payload := p[l4+8 : info.TotalLen]
		reply := make([]byte, 20+8+5+len(payload))
		reply[0], reply[8], reply[9] = 0x45, 64, packet.ProtoUDP
		binary.BigEndian.PutUint16(reply[2:4], uint16(len(reply)))
		copy(reply[12:16], info.Dst[:])
		copy(reply[16:20], info.Src[:])
		binary.BigEndian.PutUint16(reply[20:22], info.DstPort)
		binary.BigEndian.PutUint16(reply[22:24], info.SrcPort)
		binary.BigEndian.PutUint16(reply[24:26], uint16(8+5+len(payload)))
		copy(reply[28:], append([]byte("echo:"), payload...))
		packet.FixChecksums(reply)
		return reply
	case packet.ProtoTCP:
		if !info.IsSYN() {
			return nil
		}
		seq := binary.BigEndian.Uint32(p[l4+4 : l4+8])
		reply := make([]byte, 40)
		reply[0], reply[8], reply[9] = 0x45, 64, packet.ProtoTCP
		binary.BigEndian.PutUint16(reply[2:4], 40)
		copy(reply[12:16], info.Dst[:])
		copy(reply[16:20], info.Src[:])
		binary.BigEndian.PutUint16(reply[20:22], info.DstPort)
		binary.BigEndian.PutUint16(reply[22:24], info.SrcPort)
		binary.BigEndian.PutUint32(reply[28:32], seq+1) // ack
		reply[32] = 5 << 4
		reply[33] = 0x14 // RST|ACK: "connection refused"
		packet.FixChecksums(reply)
		return reply
	}
	return nil
}

func main() {
	listen := flag.String("listen", "127.0.0.1:4799", "UDP address to serve on")
	out := flag.String("out", "session.json", "where to write the relay's public key and a token")
	flag.Parse()

	key, err := proto.GenerateKey()
	if err != nil {
		log.Fatal(err)
	}
	secret := bytes.Repeat([]byte{7}, 32)
	token, err := proto.SignToken(secret, proto.Token{UserID: "selftest", Device: "selftest", Expires: time.Now().Add(24 * time.Hour).Unix()})
	if err != nil {
		log.Fatal(err)
	}

	addr, err := net.ResolveUDPAddr("udp4", *listen)
	if err != nil {
		log.Fatal(err)
	}
	conn, err := net.ListenUDP("udp4", addr)
	if err != nil {
		log.Fatal(err)
	}
	internet := &fakeInternet{replies: make(chan []byte, 256), closed: make(chan struct{})}
	server, err := relay.New(conn, internet, relay.Options{
		StaticKey: key, TokenSecret: secret, Pool: netip.MustParsePrefix("10.99.0.0/24"),
	})
	if err != nil {
		log.Fatal(err)
	}

	session, _ := json.MarshalIndent(map[string]string{
		"relay":            conn.LocalAddr().String(),
		"relay_public_key": base64.StdEncoding.EncodeToString(key.PublicKey().Bytes()),
		"token":            string(token),
	}, "", "  ")
	if err := os.WriteFile(*out, session, 0o600); err != nil {
		log.Fatal(err)
	}
	fmt.Printf("test relay on %s, session in %s\n", conn.LocalAddr(), *out)

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt)
	go func() {
		<-stop
		server.Close()
	}()
	server.Serve()
	internet.mu.Lock()
	fmt.Printf("answered %d packets\n", internet.seen)
	internet.mu.Unlock()
}
