package relay

import (
	"bytes"
	"encoding/binary"
	"errors"
	"io"
	"net"
	"net/netip"
	"sync/atomic"
	"testing"
	"time"

	"nexora.app/core/packet"
	"nexora.app/core/proto"
)

type fakeTUN struct {
	written chan []byte
	toRead  chan []byte
	closed  chan struct{}
}

func newFakeTUN() *fakeTUN {
	return &fakeTUN{written: make(chan []byte, 64), toRead: make(chan []byte, 64), closed: make(chan struct{})}
}

func (f *fakeTUN) Write(p []byte) (int, error) {
	f.written <- bytes.Clone(p)
	return len(p), nil
}

func (f *fakeTUN) Read(p []byte) (int, error) {
	select {
	case pkt := <-f.toRead:
		return copy(p, pkt), nil
	case <-f.closed:
		return 0, io.EOF
	}
}

func (f *fakeTUN) Close() error {
	select {
	case <-f.closed:
	default:
		close(f.closed)
	}
	return nil
}

type harness struct {
	t      *testing.T
	server *Server
	tun    *fakeTUN
	addr   *net.UDPAddr
	secret []byte
	clock  atomic.Int64
}

func newHarness(t *testing.T, pool string) *harness {
	t.Helper()
	key, _ := proto.GenerateKey()
	conn, err := net.ListenUDP("udp4", &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1)})
	if err != nil {
		t.Fatal(err)
	}
	h := &harness{t: t, tun: newFakeTUN(), addr: conn.LocalAddr().(*net.UDPAddr), secret: []byte("0123456789abcdef-secret")}
	h.clock.Store(time.Now().UnixNano())
	h.server, err = New(conn, h.tun, Options{
		StaticKey:   key,
		TokenSecret: h.secret,
		Pool:        netip.MustParsePrefix(pool),
		IdleTimeout: time.Minute,
		Now:         func() time.Time { return time.Unix(0, h.clock.Load()) },
	})
	if err != nil {
		t.Fatal(err)
	}
	go h.server.Serve()
	t.Cleanup(h.server.Close)
	return h
}

type client struct {
	t       *testing.T
	conn    *net.UDPConn
	session *proto.Session
	welcome proto.Welcome
}

func (h *harness) token(uid, dev string, ttl time.Duration) []byte {
	signed, err := proto.SignToken(h.secret, proto.Token{UserID: uid, Device: dev, Expires: time.Unix(0, h.clock.Load()).Add(ttl).Unix()})
	if err != nil {
		h.t.Fatal(err)
	}
	return signed
}

func (h *harness) dial() *net.UDPConn {
	conn, err := net.DialUDP("udp4", nil, h.addr)
	if err != nil {
		h.t.Fatal(err)
	}
	h.t.Cleanup(func() { conn.Close() })
	return conn
}

func recv(t *testing.T, conn *net.UDPConn) []byte {
	t.Helper()
	buf := make([]byte, 2048)
	conn.SetReadDeadline(time.Now().Add(2 * time.Second))
	n, err := conn.Read(buf)
	if err != nil {
		t.Fatalf("no reply from relay: %v", err)
	}
	return buf[:n]
}

func expectSilence(t *testing.T, conn *net.UDPConn) {
	t.Helper()
	conn.SetReadDeadline(time.Now().Add(150 * time.Millisecond))
	if n, err := conn.Read(make([]byte, 2048)); err == nil {
		t.Fatalf("expected no reply, got %d bytes", n)
	}
}

func (h *harness) connect(uid, dev string) *client {
	h.t.Helper()
	conn := h.dial()
	hs, hello, err := proto.NewClientHello(h.server.opts.StaticKey.PublicKey(), h.token(uid, dev, time.Hour))
	if err != nil {
		h.t.Fatal(err)
	}
	conn.Write(hello)
	session, welcome, err := hs.Finish(recv(h.t, conn))
	if err != nil {
		h.t.Fatalf("handshake: %v", err)
	}
	return &client{t: h.t, conn: conn, session: session, welcome: welcome}
}

func udpPacket(src, dst [4]byte, srcPort, dstPort uint16, payload string) []byte {
	b := make([]byte, 28+len(payload))
	b[0] = 0x45
	binary.BigEndian.PutUint16(b[2:4], uint16(len(b)))
	b[8] = 64
	b[9] = packet.ProtoUDP
	copy(b[12:16], src[:])
	copy(b[16:20], dst[:])
	binary.BigEndian.PutUint16(b[20:22], srcPort)
	binary.BigEndian.PutUint16(b[22:24], dstPort)
	binary.BigEndian.PutUint16(b[24:26], uint16(8+len(payload)))
	copy(b[28:], payload)
	packet.FixChecksums(b)
	return b
}

func expectTUNWrite(t *testing.T, tun *fakeTUN) []byte {
	t.Helper()
	select {
	case pkt := <-tun.written:
		return pkt
	case <-time.After(2 * time.Second):
		t.Fatal("relay did not forward the packet to the TUN device")
		return nil
	}
}

func expectNoTUNWrite(t *testing.T, tun *fakeTUN) {
	t.Helper()
	select {
	case pkt := <-tun.written:
		t.Fatalf("relay forwarded a packet it should have dropped: % x", pkt[:20])
	case <-time.After(150 * time.Millisecond):
	}
}

var gameServer = [4]byte{203, 0, 113, 9}

func TestRelayForwardsClientPacketsAndReturnsReplies(t *testing.T) {
	h := newHarness(t, "10.66.0.0/24")
	c := h.connect("alice", "pc")
	if c.welcome.VirtualIP != [4]byte{10, 66, 0, 2} || c.welcome.MTU != proto.InnerMTU {
		t.Fatalf("welcome = %+v", c.welcome)
	}

	out := udpPacket(c.welcome.VirtualIP, gameServer, 50000, 27015, "to game")
	c.conn.Write(c.session.Seal(nil, proto.TypeData, out))
	if got := expectTUNWrite(t, h.tun); !bytes.Equal(got, out) {
		t.Fatalf("TUN got % x, want % x", got, out)
	}

	back := udpPacket(gameServer, c.welcome.VirtualIP, 27015, 50000, "from game")
	h.tun.toRead <- back
	typ, payload, err := c.session.Open(nil, recv(t, c.conn))
	if err != nil || typ != proto.TypeData || !bytes.Equal(payload, back) {
		t.Fatalf("client got typ=%d err=%v payload=% x", typ, err, payload)
	}
}

func TestRelayDropsSpoofedPrivateAndOversizedPackets(t *testing.T) {
	h := newHarness(t, "10.66.0.0/24")
	c := h.connect("alice", "pc")
	send := func(pkt []byte) { c.conn.Write(c.session.Seal(nil, proto.TypeData, pkt)) }

	// Another client's address, or any made-up source.
	send(udpPacket([4]byte{10, 66, 0, 3}, gameServer, 50000, 27015, "spoof"))
	expectNoTUNWrite(t, h.tun)
	// The relay's own private network must not be reachable through it.
	send(udpPacket(c.welcome.VirtualIP, [4]byte{192, 168, 0, 1}, 50000, 80, "lan"))
	expectNoTUNWrite(t, h.tun)
	send(udpPacket(c.welcome.VirtualIP, [4]byte{10, 66, 0, 1}, 50000, 22, "gateway"))
	expectNoTUNWrite(t, h.tun)
	send(udpPacket(c.welcome.VirtualIP, [4]byte{127, 0, 0, 1}, 50000, 80, "loopback"))
	expectNoTUNWrite(t, h.tun)
	send(udpPacket(c.welcome.VirtualIP, gameServer, 50000, 27015, string(make([]byte, 1500))))
	expectNoTUNWrite(t, h.tun)
	send([]byte("not an ip packet"))
	expectNoTUNWrite(t, h.tun)

	// The session still works after all of that.
	ok := udpPacket(c.welcome.VirtualIP, gameServer, 50000, 27015, "fine")
	send(ok)
	if got := expectTUNWrite(t, h.tun); !bytes.Equal(got, ok) {
		t.Fatal("valid packet after rejected ones was not forwarded intact")
	}
}

func TestRelayRejectsBadAndExpiredTokens(t *testing.T) {
	h := newHarness(t, "10.66.0.0/24")
	try := func(token []byte) error {
		conn := h.dial()
		hs, hello, _ := proto.NewClientHello(h.server.opts.StaticKey.PublicKey(), token)
		conn.Write(hello)
		_, _, err := hs.Finish(recv(t, conn))
		return err
	}
	var rejected *proto.RejectError

	forged, _ := proto.SignToken([]byte("someone-elses-secret"), proto.Token{UserID: "mallory", Expires: time.Now().Add(time.Hour).Unix()})
	if err := try(forged); !errors.As(err, &rejected) || rejected.Code != proto.RejectBadToken {
		t.Fatalf("forged token: %v", err)
	}
	if err := try(h.token("alice", "pc", -time.Minute)); !errors.As(err, &rejected) || rejected.Code != proto.RejectExpired {
		t.Fatalf("expired token: %v", err)
	}
	if h.server.SessionCount() != 0 {
		t.Fatalf("rejected handshakes left %d sessions", h.server.SessionCount())
	}
}

func TestReconnectKeepsAddressAndInvalidatesOldSession(t *testing.T) {
	h := newHarness(t, "10.66.0.0/24")
	first := h.connect("alice", "pc")
	other := h.connect("bob", "pc")
	second := h.connect("alice", "pc")

	if second.welcome.VirtualIP != first.welcome.VirtualIP {
		t.Fatalf("reconnect changed address %v -> %v", first.welcome.VirtualIP, second.welcome.VirtualIP)
	}
	if other.welcome.VirtualIP == first.welcome.VirtualIP {
		t.Fatal("two users share an address")
	}
	if h.server.SessionCount() != 2 {
		t.Fatalf("sessions = %d, want 2", h.server.SessionCount())
	}

	stale := udpPacket(first.welcome.VirtualIP, gameServer, 50000, 27015, "stale")
	first.conn.Write(first.session.Seal(nil, proto.TypeData, stale))
	expectNoTUNWrite(t, h.tun)

	// Replies now follow the new session's socket.
	back := udpPacket(gameServer, second.welcome.VirtualIP, 27015, 50000, "reply")
	h.tun.toRead <- back
	if _, payload, err := second.session.Open(nil, recv(t, second.conn)); err != nil || !bytes.Equal(payload, back) {
		t.Fatalf("new session did not receive the reply: %v", err)
	}
}

func TestRetransmittedHelloGetsTheSameWelcome(t *testing.T) {
	h := newHarness(t, "10.66.0.0/24")
	conn := h.dial()
	hs, hello, _ := proto.NewClientHello(h.server.opts.StaticKey.PublicKey(), h.token("alice", "pc", time.Hour))

	conn.Write(hello)
	firstWelcome := recv(t, conn)
	conn.Write(hello)
	secondWelcome := recv(t, conn)
	if !bytes.Equal(firstWelcome, secondWelcome) {
		t.Fatal("a retransmitted HELLO produced a different session")
	}
	// A client that only saw the first welcome must still have a live session.
	session, welcome, err := hs.Finish(firstWelcome)
	if err != nil {
		t.Fatal(err)
	}
	pkt := udpPacket(welcome.VirtualIP, gameServer, 50000, 27015, "x")
	conn.Write(session.Seal(nil, proto.TypeData, pkt))
	expectTUNWrite(t, h.tun)
}

func TestPingProbeByeAndIdleReap(t *testing.T) {
	h := newHarness(t, "10.66.0.0/24")
	c := h.connect("alice", "pc")

	c.conn.Write(c.session.Seal(nil, proto.TypePing, []byte("12345678")))
	if typ, payload, err := c.session.Open(nil, recv(t, c.conn)); err != nil || typ != proto.TypePong || string(payload) != "12345678" {
		t.Fatalf("pong: typ=%d payload=%q err=%v", typ, payload, err)
	}

	prober := h.dial()
	prober.Write(append([]byte{proto.TypeProbe}, "ABCDEFGH"...))
	if reply := recv(t, prober); reply[0] != proto.TypeProbeReply || string(reply[1:]) != "ABCDEFGH" {
		t.Fatalf("probe reply = % x", reply)
	}
	// Anything that isn't exactly a probe gets no answer at all.
	prober.Write(append([]byte{proto.TypeProbe}, make([]byte, 400)...))
	expectSilence(t, prober)

	idle := h.connect("carol", "pc")
	h.clock.Add(int64(2 * time.Minute))
	// alice is active after the clock jump, carol is not.
	c.conn.Write(c.session.Seal(nil, proto.TypePing, []byte("12345678")))
	recv(t, c.conn)
	h.server.reapIdle()
	if h.server.SessionCount() != 1 {
		t.Fatalf("after reap sessions = %d, want 1", h.server.SessionCount())
	}
	idle.conn.Write(idle.session.Seal(nil, proto.TypePing, []byte("12345678")))
	expectSilence(t, idle.conn)

	c.conn.Write(c.session.Seal(nil, proto.TypeBye, nil))
	deadline := time.Now().Add(2 * time.Second)
	for h.server.SessionCount() != 0 && time.Now().Before(deadline) {
		time.Sleep(10 * time.Millisecond)
	}
	if h.server.SessionCount() != 0 {
		t.Fatal("BYE did not close the session")
	}
	// The freed address is handed out again.
	if again := h.connect("dave", "pc"); again.welcome.VirtualIP != c.welcome.VirtualIP && again.welcome.VirtualIP != idle.welcome.VirtualIP {
		t.Fatalf("freed addresses were not reused: got %v", again.welcome.VirtualIP)
	}
}

func TestPoolExhaustionIsRejectedCleanly(t *testing.T) {
	h := newHarness(t, "10.66.0.0/29") // 8 addresses: 5 usable for clients
	for i := range 5 {
		h.connect("user", string(rune('a'+i)))
	}
	conn := h.dial()
	hs, hello, _ := proto.NewClientHello(h.server.opts.StaticKey.PublicKey(), h.token("user", "overflow", time.Hour))
	conn.Write(hello)
	var rejected *proto.RejectError
	if _, _, err := hs.Finish(recv(t, conn)); !errors.As(err, &rejected) || rejected.Code != proto.RejectFull {
		t.Fatalf("overflow handshake: %v", err)
	}
}
