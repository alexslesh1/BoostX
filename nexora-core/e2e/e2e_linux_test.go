//go:build linux

// Package e2e runs the real engine against the real relay, with the Linux
// kernel doing real NAT towards a "game server" in its own network
// namespace. Only the Windows packet capture is substituted (by a fake that
// plays the role of a game's sockets), so this exercises every byte of the
// tunnel path that is not WinDivert itself.
//
// It needs root, /dev/net/tun, iproute2 and iptables:
//
//	sudo go test ./e2e/ -v
package e2e

import (
	"bytes"
	"encoding/base64"
	"encoding/binary"
	"errors"
	"fmt"
	"io"
	"net"
	"net/netip"
	"os"
	"os/exec"
	"strings"
	"sync"
	"testing"
	"time"

	"nexora.app/core/engine"
	"nexora.app/core/packet"
	"nexora.app/core/proto"
	"nexora.app/core/relay"
)

const (
	echoEnv   = "NEXORA_E2E_ECHO_ADDR"
	nsName    = "nxgame"
	tunName   = "nxtest0"
	hostVeth  = "nxveth0"
	nsVeth    = "nxveth1"
	hostAddr  = "198.51.100.1"
	gameAddr  = "198.51.100.2"
	gamePort  = 27015
	poolCIDR  = "10.99.0.0/24"
	gameExe   = `C:\Games\Shooter\Binaries\shooter.exe`
	otherExe  = `C:\Program Files\Browser\browser.exe`
	gameRule  = "Shooter"
	gamePortU = 51000
	gamePortT = 51001
	otherPort = 52000
)

var (
	lanIP     = [4]byte{192, 168, 1, 50}
	gameIP    = [4]byte{198, 51, 100, 2}
	captureIf = engine.Meta{IfIdx: 7, SubIfIdx: 0}
)

// TestMain doubles as the game server: `ip netns exec` re-runs this binary
// inside the namespace with echoEnv set.
func TestMain(m *testing.M) {
	if addr := os.Getenv(echoEnv); addr != "" {
		runEchoServer(addr)
		return
	}
	os.Exit(m.Run())
}

// runEchoServer answers "from <peer address>|<payload>" on UDP and TCP, so
// the test can see which source address the game server observed.
func runEchoServer(addr string) {
	udp, err := net.ListenPacket("udp4", addr)
	if err != nil {
		fmt.Fprintln(os.Stderr, "echo udp:", err)
		os.Exit(1)
	}
	tcp, err := net.Listen("tcp4", addr)
	if err != nil {
		fmt.Fprintln(os.Stderr, "echo tcp:", err)
		os.Exit(1)
	}
	go func() {
		buf := make([]byte, 65535)
		for {
			n, peer, err := udp.ReadFrom(buf)
			if err != nil {
				return
			}
			udp.WriteTo(append([]byte("from "+peer.String()+"|"), buf[:n]...), peer)
		}
	}()
	for {
		conn, err := tcp.Accept()
		if err != nil {
			return
		}
		go func() {
			defer conn.Close()
			fmt.Fprintf(conn, "from %s|", conn.RemoteAddr())
			io.Copy(conn, conn)
		}()
	}
}

func run(t *testing.T, name string, args ...string) {
	t.Helper()
	if out, err := exec.Command(name, args...).CombinedOutput(); err != nil {
		t.Fatalf("%s %s: %v\n%s", name, strings.Join(args, " "), err, out)
	}
}

func tryRun(name string, args ...string) { exec.Command(name, args...).Run() }

type capturedPacket struct {
	pkt  []byte
	meta engine.Meta
}

// fakeCapture stands in for WinDivert: the test pushes "outbound packets
// from applications" in, and observes what the engine reinjected (left
// alone) or injected inbound (delivered back to the application).
type fakeCapture struct {
	outbound   chan capturedPacket
	reinjected chan []byte
	inbound    chan capturedPacket
	closed     chan struct{}
	once       sync.Once
}

func newFakeCapture() *fakeCapture {
	return &fakeCapture{
		outbound:   make(chan capturedPacket, 64),
		reinjected: make(chan []byte, 64),
		inbound:    make(chan capturedPacket, 256),
		closed:     make(chan struct{}),
	}
}

func (c *fakeCapture) Recv(buf []byte) (int, engine.Meta, error) {
	select {
	case p := <-c.outbound:
		return copy(buf, p.pkt), p.meta, nil
	case <-c.closed:
		return 0, engine.Meta{}, errors.New("capture closed")
	}
}

func (c *fakeCapture) Reinject(pkt []byte, _ engine.Meta) error {
	c.reinjected <- bytes.Clone(pkt)
	return nil
}

func (c *fakeCapture) InjectInbound(pkt []byte, meta engine.Meta) error {
	c.inbound <- capturedPacket{pkt: bytes.Clone(pkt), meta: meta}
	return nil
}

func (c *fakeCapture) Close() error {
	c.once.Do(func() { close(c.closed) })
	return nil
}

// fakeResolver stands in for the Windows "which process owns this port" lookup.
type fakeResolver map[uint16]string

func (r fakeResolver) Owner(_ uint8, _ [4]byte, port uint16) (uint32, string, bool) {
	exe, ok := r[port]
	return uint32(port), exe, ok
}

type world struct {
	t       *testing.T
	capture *fakeCapture
	engine  *engine.Engine
}

func setup(t *testing.T) *world {
	t.Helper()
	if os.Geteuid() != 0 {
		t.Skip("needs root (TUN device, network namespace, iptables)")
	}
	for _, tool := range []string{"ip", "iptables"} {
		if _, err := exec.LookPath(tool); err != nil {
			t.Skipf("needs %s", tool)
		}
	}

	// The "internet": a game server in its own namespace, reachable from
	// the relay host only over a veth link.
	tryRun("ip", "netns", "del", nsName)
	tryRun("ip", "link", "del", hostVeth)
	run(t, "ip", "netns", "add", nsName)
	t.Cleanup(func() { tryRun("ip", "netns", "del", nsName) })
	run(t, "ip", "link", "add", hostVeth, "type", "veth", "peer", "name", nsVeth)
	t.Cleanup(func() { tryRun("ip", "link", "del", hostVeth) })
	run(t, "ip", "link", "set", nsVeth, "netns", nsName)
	run(t, "ip", "addr", "add", hostAddr+"/24", "dev", hostVeth)
	run(t, "ip", "link", "set", hostVeth, "up")
	run(t, "ip", "netns", "exec", nsName, "ip", "addr", "add", gameAddr+"/24", "dev", nsVeth)
	run(t, "ip", "netns", "exec", nsName, "ip", "link", "set", nsVeth, "up")
	run(t, "ip", "netns", "exec", nsName, "ip", "link", "set", "lo", "up")
	// Deliberately no route back to the tunnel pool inside the namespace:
	// replies can only find their way home if the relay really did NAT.

	self, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	echo := exec.Command("ip", "netns", "exec", nsName, self)
	echo.Env = append(os.Environ(), fmt.Sprintf("%s=%s:%d", echoEnv, gameAddr, gamePort))
	echo.Stderr = os.Stderr
	if err := echo.Start(); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { echo.Process.Kill(); echo.Wait() })
	waitForTCP(t, fmt.Sprintf("%s:%d", gameAddr, gamePort))

	// The relay, exactly as cmd/nexora-relay assembles it.
	pool := netip.MustParsePrefix(poolCIDR)
	tun, err := relay.OpenTUN(tunName, pool, proto.InnerMTU)
	if err != nil {
		t.Fatalf("OpenTUN: %v", err)
	}
	firewall, err := relay.SetupFirewall(tunName, pool)
	if err != nil {
		tun.Close()
		t.Fatalf("SetupFirewall: %v", err)
	}
	t.Cleanup(firewall.Remove)
	relayKey, _ := proto.GenerateKey()
	secret := []byte("e2e-shared-token-secret")
	relayConn, err := net.ListenUDP("udp4", &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1)})
	if err != nil {
		t.Fatal(err)
	}
	server, err := relay.New(relayConn, tun, relay.Options{StaticKey: relayKey, TokenSecret: secret, Pool: pool})
	if err != nil {
		t.Fatal(err)
	}
	go server.Serve()
	t.Cleanup(server.Close)

	// The engine, with only capture and process lookup substituted.
	token, _ := proto.SignToken(secret, proto.Token{UserID: "e2e", Device: "pc", Expires: time.Now().Add(time.Hour).Unix()})
	tunnel, err := engine.NewTunnel(relayConn.LocalAddr().String(),
		base64.StdEncoding.EncodeToString(relayKey.PublicKey().Bytes()), string(token))
	if err != nil {
		t.Fatal(err)
	}
	capture := newFakeCapture()
	resolver := fakeResolver{gamePortU: gameExe, gamePortT: gameExe, otherPort: otherExe}
	eng := engine.New(capture, resolver, tunnel, []engine.Rule{{Name: gameRule, Dirs: []string{`C:\Games\Shooter`}}})
	go eng.Run()
	t.Cleanup(eng.Close)

	deadline := time.Now().Add(5 * time.Second)
	for !eng.Status().Tunnel.Connected {
		if time.Now().After(deadline) {
			t.Fatalf("tunnel never connected: %+v", eng.Status().Tunnel)
		}
		time.Sleep(20 * time.Millisecond)
	}
	return &world{t: t, capture: capture, engine: eng}
}

func waitForTCP(t *testing.T, addr string) {
	t.Helper()
	deadline := time.Now().Add(5 * time.Second)
	for {
		conn, err := net.DialTimeout("tcp4", addr, 200*time.Millisecond)
		if err == nil {
			conn.Close()
			return
		}
		if time.Now().After(deadline) {
			t.Fatalf("game server never came up on %s: %v", addr, err)
		}
		time.Sleep(50 * time.Millisecond)
	}
}

func ipHeader(proto uint8, src, dst [4]byte, id uint16, l4len int) []byte {
	b := make([]byte, 20+l4len)
	b[0] = 0x45
	binary.BigEndian.PutUint16(b[2:4], uint16(len(b)))
	binary.BigEndian.PutUint16(b[4:6], id)
	b[6] = 0x40
	b[8] = 128
	b[9] = proto
	copy(b[12:16], src[:])
	copy(b[16:20], dst[:])
	return b
}

// appUDP builds a datagram the way a Windows capture hands it over: with a
// transport checksum the NIC was supposed to fill in later.
func appUDP(srcPort uint16, dst [4]byte, dstPort uint16, payload []byte) []byte {
	b := ipHeader(packet.ProtoUDP, lanIP, dst, 1, 8+len(payload))
	binary.BigEndian.PutUint16(b[20:22], srcPort)
	binary.BigEndian.PutUint16(b[22:24], dstPort)
	binary.BigEndian.PutUint16(b[24:26], uint16(8+len(payload)))
	binary.BigEndian.PutUint16(b[26:28], 0x1111)
	copy(b[28:], payload)
	return b
}

func (w *world) send(pkt []byte) {
	w.capture.outbound <- capturedPacket{pkt: pkt, meta: captureIf}
}

func (w *world) expectInbound(what string) capturedPacket {
	w.t.Helper()
	select {
	case p := <-w.capture.inbound:
		return p
	case <-time.After(3 * time.Second):
		w.t.Fatalf("timed out waiting for %s to come back through the tunnel", what)
		return capturedPacket{}
	}
}

func (w *world) expectReinjected(what string) []byte {
	w.t.Helper()
	select {
	case pkt := <-w.capture.reinjected:
		return pkt
	case <-time.After(2 * time.Second):
		w.t.Fatalf("%s was not passed through untouched", what)
		return nil
	}
}

// valid checks checksums the way a receiving stack would.
func valid(t *testing.T, pkt []byte) packet.Info {
	t.Helper()
	info, err := packet.Parse(pkt)
	if err != nil {
		t.Fatalf("unparseable packet: %v", err)
	}
	fixed := bytes.Clone(pkt)
	if err := packet.FixChecksums(fixed); err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(fixed, pkt) {
		t.Fatalf("packet delivered to the application has bad checksums")
	}
	return info
}

func TestGameUDPGoesThroughRelayAndComesBack(t *testing.T) {
	w := setup(t)

	w.send(appUDP(gamePortU, gameIP, gamePort, []byte("player input")))
	reply := w.expectInbound("the game server's UDP reply")
	info := valid(t, reply.pkt)

	if info.Src != gameIP || info.SrcPort != gamePort {
		t.Fatalf("reply source = %v:%d, want the game server", info.Src, info.SrcPort)
	}
	if info.Dst != lanIP || info.DstPort != gamePortU {
		t.Fatalf("reply destination = %v:%d, want the application's own %v:%d", info.Dst, info.DstPort, lanIP, gamePortU)
	}
	if reply.meta != captureIf {
		t.Fatalf("reply injected on %+v, want the interface it was captured on %+v", reply.meta, captureIf)
	}
	body := string(reply.pkt[28:info.TotalLen])
	// The game server must have seen the relay's address, not the client's
	// tunnel or LAN address: that is the whole point of the relay.
	if !strings.HasPrefix(body, "from "+hostAddr+":") || !strings.HasSuffix(body, "|player input") {
		t.Fatalf("game server saw %q, want a packet from the relay %s", body, hostAddr)
	}

	select {
	case pkt := <-w.capture.reinjected:
		t.Fatalf("a tunneled packet also leaked out directly: % x", pkt[:28])
	case <-time.After(100 * time.Millisecond):
	}

	status := w.engine.Status()
	if len(status.Flows) != 1 {
		t.Fatalf("flows = %+v, want exactly the game's", status.Flows)
	}
	flow := status.Flows[0]
	if flow.App != gameRule || flow.Exe != "shooter.exe" || flow.Protocol != "UDP" || flow.LocalPort != gamePortU ||
		flow.Remote != fmt.Sprintf("%s:%d", gameAddr, gamePort) || flow.BytesOut == 0 || flow.BytesIn == 0 {
		t.Fatalf("flow status = %+v", flow)
	}
}

func TestOtherProgramsAndLocalTrafficAreLeftAlone(t *testing.T) {
	w := setup(t)

	browser := appUDP(otherPort, gameIP, gamePort, []byte("not a game"))
	w.send(bytes.Clone(browser))
	if got := w.expectReinjected("another program's packet"); !bytes.Equal(got, browser) {
		t.Fatal("another program's packet was modified")
	}

	lan := appUDP(gamePortU, [4]byte{192, 168, 1, 1}, 53, []byte("lan"))
	w.send(bytes.Clone(lan))
	if got := w.expectReinjected("the game's own LAN packet"); !bytes.Equal(got, lan) {
		t.Fatal("LAN packet was modified")
	}

	unknown := appUDP(60000, gameIP, gamePort, []byte("unknown owner"))
	w.send(bytes.Clone(unknown))
	if got := w.expectReinjected("a packet whose owner is unknown"); !bytes.Equal(got, unknown) {
		t.Fatal("packet with unknown owner was modified")
	}

	select {
	case p := <-w.capture.inbound:
		t.Fatalf("something was tunneled that should not have been: % x", p.pkt[:28])
	case <-time.After(300 * time.Millisecond):
	}
	if flows := w.engine.Status().Flows; len(flows) != 0 {
		t.Fatalf("flows = %+v, want none", flows)
	}
}

func TestLargeUDPDatagramIsFragmentedAndReassembled(t *testing.T) {
	w := setup(t)
	payload := bytes.Repeat([]byte("0123456789abcdef"), 150) // 2400 bytes: over the tunnel MTU

	big := appUDP(gamePortU, gameIP, gamePort, payload)
	big[6] = 0 // the application did not forbid fragmentation
	w.send(big)

	var body []byte
	var total int
	for i := 0; ; i++ {
		frag := w.expectInbound("a fragment of the large UDP reply")
		info, err := packet.Parse(frag.pkt)
		if err != nil {
			t.Fatal(err)
		}
		if info.Dst != lanIP || info.Src != gameIP {
			t.Fatalf("fragment %d addressed %v -> %v", i, info.Src, info.Dst)
		}
		if len(frag.pkt) > proto.InnerMTU {
			t.Fatalf("fragment %d is %d bytes, over the tunnel MTU", i, len(frag.pkt))
		}
		field := binary.BigEndian.Uint16(frag.pkt[6:8])
		offset := int(field&0x1FFF) * 8
		if offset != len(body) {
			t.Fatalf("fragment %d out of order: offset %d, have %d", i, offset, len(body))
		}
		body = append(body, frag.pkt[info.HeaderLen:info.TotalLen]...)
		if field&0x2000 == 0 {
			total = len(body)
			break
		}
	}
	if total < 8 {
		t.Fatal("no UDP header in reassembled reply")
	}

	// Verify the reassembled datagram's UDP checksum against the address
	// the application will see, exactly as its network stack will.
	rebuilt := ipHeader(packet.ProtoUDP, gameIP, lanIP, 9, len(body))
	rebuilt[6] = 0
	copy(rebuilt[20:], body)
	want := bytes.Clone(rebuilt)
	if err := packet.FixChecksums(want); err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(want[26:28], rebuilt[26:28]) {
		t.Fatalf("reassembled UDP checksum %x is wrong, want %x", rebuilt[26:28], want[26:28])
	}
	text := string(body[8:])
	if !strings.HasPrefix(text, "from "+hostAddr+":") || !strings.HasSuffix(text, "|"+string(payload)) {
		t.Fatalf("large datagram did not survive the round trip (%d bytes back)", len(text))
	}
}

// tcpPeer is a deliberately tiny TCP endpoint standing in for the game's own
// socket: just enough to open a connection and exchange data with a real
// kernel TCP stack on the far side of the relay.
type tcpPeer struct {
	w       *world
	port    uint16
	seq     uint32
	ack     uint32
	recvd   []byte
	peerMSS uint16
}

func (p *tcpPeer) segment(flags uint8, options, payload []byte) []byte {
	l4len := 20 + len(options) + len(payload)
	b := ipHeader(packet.ProtoTCP, lanIP, gameIP, uint16(p.seq), l4len)
	tcp := b[20:]
	binary.BigEndian.PutUint16(tcp[0:2], p.port)
	binary.BigEndian.PutUint16(tcp[2:4], gamePort)
	binary.BigEndian.PutUint32(tcp[4:8], p.seq)
	binary.BigEndian.PutUint32(tcp[8:12], p.ack)
	tcp[12] = uint8((20+len(options))/4) << 4
	tcp[13] = flags
	binary.BigEndian.PutUint16(tcp[14:16], 65535)
	binary.BigEndian.PutUint16(tcp[16:18], 0x2222) // offloaded: not a real checksum
	copy(tcp[20:], options)
	copy(tcp[20+len(options):], payload)
	return b
}

// read consumes inbound segments until want bytes of stream have arrived.
func (p *tcpPeer) read(want int) {
	p.w.t.Helper()
	for len(p.recvd) < want {
		in := p.w.expectInbound("TCP data from the game server")
		info := valid(p.w.t, in.pkt)
		if info.Dst != lanIP || info.DstPort != p.port || info.Src != gameIP {
			p.w.t.Fatalf("TCP segment addressed %v:%d -> %v:%d", info.Src, info.SrcPort, info.Dst, info.DstPort)
		}
		if len(in.pkt) > proto.InnerMTU {
			p.w.t.Fatalf("inbound TCP segment of %d bytes exceeds the tunnel MTU", len(in.pkt))
		}
		tcp := in.pkt[info.HeaderLen:info.TotalLen]
		data := tcp[int(tcp[12]>>4)*4:]
		seq := binary.BigEndian.Uint32(tcp[4:8])
		if len(data) == 0 {
			continue
		}
		if seq == p.ack {
			p.recvd = append(p.recvd, data...)
			p.ack += uint32(len(data))
		}
		p.w.send(p.segment(0x10, nil, nil))
	}
}

func TestGameTCPHandshakeDataAndOffloadedGiantSegment(t *testing.T) {
	w := setup(t)
	peer := &tcpPeer{w: w, port: gamePortT, seq: 0xFFFFF000}

	mssOption := []byte{2, 4, 0x05, 0xB4} // MSS 1460, as on an Ethernet LAN
	w.send(peer.segment(0x02, mssOption, nil))
	peer.seq++

	synAck := w.expectInbound("SYN-ACK")
	info := valid(t, synAck.pkt)
	tcp := synAck.pkt[info.HeaderLen:info.TotalLen]
	if tcp[13]&0x12 != 0x12 {
		t.Fatalf("expected SYN-ACK, got flags %#x", tcp[13])
	}
	if got := binary.BigEndian.Uint32(tcp[8:12]); got != peer.seq {
		t.Fatalf("SYN-ACK acknowledges %#x, want %#x", got, peer.seq)
	}
	for opts := tcp[20 : int(tcp[12]>>4)*4]; len(opts) >= 4; {
		if opts[0] == 1 {
			opts = opts[1:]
			continue
		}
		if opts[0] == 2 {
			peer.peerMSS = binary.BigEndian.Uint16(opts[2:4])
			break
		}
		opts = opts[opts[1]:]
	}
	// Both directions must be clamped so no segment outgrows the tunnel.
	if peer.peerMSS == 0 || int(peer.peerMSS) > proto.InnerMTU-40 {
		t.Fatalf("SYN-ACK MSS = %d, want it clamped below %d", peer.peerMSS, proto.InnerMTU-40)
	}
	peer.ack = binary.BigEndian.Uint32(tcp[4:8]) + 1
	w.send(peer.segment(0x10, nil, nil))

	// The server greets with the address it sees us coming from.
	greeting := "from " + hostAddr + ":"
	peer.read(len(greeting))
	if !strings.HasPrefix(string(peer.recvd), greeting) {
		t.Fatalf("game server saw the TCP connection from %q, want the relay %s", peer.recvd, hostAddr)
	}
	bar := bytes.IndexByte(peer.recvd, '|')
	for bar < 0 {
		peer.read(len(peer.recvd) + 1)
		bar = bytes.IndexByte(peer.recvd, '|')
	}
	header := len(peer.recvd[:bar+1])

	// One 6000-byte "packet", as Windows hands over when the NIC does
	// large-send offload. The engine has to cut it into real segments that
	// a real TCP stack on the far side accepts and acknowledges.
	payload := make([]byte, 6000)
	for i := range payload {
		payload[i] = byte('a' + i%26)
	}
	w.send(peer.segment(0x18, nil, payload))
	peer.seq += uint32(len(payload))

	peer.read(header + len(payload))
	if !bytes.Equal(peer.recvd[header:header+len(payload)], payload) {
		t.Fatal("data echoed back through the relay does not match what was sent")
	}

	flows := w.engine.Status().Flows
	if len(flows) != 1 || flows[0].Protocol != "TCP" || flows[0].BytesIn < 6000 || flows[0].BytesOut < 6000 {
		t.Fatalf("flow status = %+v", flows)
	}
	w.send(peer.segment(0x14, nil, nil)) // RST: tidy up the far side
}

func TestProbeMeasuresRelay(t *testing.T) {
	relayKey, _ := proto.GenerateKey()
	conn, err := net.ListenUDP("udp4", &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1)})
	if err != nil {
		t.Fatal(err)
	}
	reader, writer := io.Pipe()
	server, err := relay.New(conn, pipeTUN{reader, writer}, relay.Options{
		StaticKey: relayKey, TokenSecret: []byte("0123456789abcdef"), Pool: netip.MustParsePrefix("10.98.0.0/24"),
	})
	if err != nil {
		t.Fatal(err)
	}
	go server.Serve()
	defer server.Close()

	results := engine.Probe([]string{"127.0.0.1:9", conn.LocalAddr().String()}, 3, 300*time.Millisecond)
	if len(results) != 2 {
		t.Fatalf("results = %+v", results)
	}
	if !results[0].OK || results[0].Relay != conn.LocalAddr().String() || results[0].Lost != 0 {
		t.Fatalf("live relay should sort first and answer every probe: %+v", results)
	}
	if results[1].OK {
		t.Fatalf("dead relay reported reachable: %+v", results[1])
	}
}

type pipeTUN struct {
	*io.PipeReader
	*io.PipeWriter
}

func (p pipeTUN) Close() error {
	p.PipeReader.Close()
	return p.PipeWriter.Close()
}
