package engine

import (
	"bytes"
	"encoding/base64"
	"encoding/binary"
	"encoding/json"
	"errors"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"net/netip"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"nexora.app/core/packet"
	"nexora.app/core/proto"
	"nexora.app/core/relay"
)

func TestRulesMatchByExeNameAndInstallFolder(t *testing.T) {
	rules := newRuleSet([]Rule{
		{Name: "Roblox", Exes: []string{"RobloxPlayerBeta.exe"}},
		{Name: "Shooter", Dirs: []string{`C:\Games\Shooter\`, "D:/Epic/Shooter"}},
		{Name: "Empty", Dirs: []string{""}},
	})
	cases := map[string]string{
		`C:\Users\me\AppData\Local\Roblox\robloxplayerbeta.EXE`: "Roblox",
		`C:\Games\Shooter\Binaries\Win64\shooter.exe`:           "Shooter",
		`c:\games\shooter\anticheat\service.exe`:                "Shooter",
		`D:\Epic\Shooter\launcher.exe`:                          "Shooter",
		`C:\Games\ShooterTwo\game.exe`:                          "", // a folder name prefix is not the folder
		`C:\Windows\System32\svchost.exe`:                       "",
		``:                                                      "",
	}
	for path, want := range cases {
		if got := rules.match(path); got != want {
			t.Errorf("match(%q) = %q, want %q", path, got, want)
		}
	}
}

func ownerTable(layout ownerRow, rows ...[3]uint32) []byte {
	table := binary.LittleEndian.AppendUint32(nil, uint32(len(rows)))
	for _, r := range rows {
		row := make([]byte, layout.size)
		binary.BigEndian.PutUint32(row[layout.addrAt:], r[0])
		binary.BigEndian.PutUint16(row[layout.portAt:], uint16(r[1])) // network order, low 16 bits
		binary.LittleEndian.PutUint32(row[layout.pidAt:], r[2])
		table = append(table, row...)
	}
	return table
}

func TestFindOwnerInWindowsSocketTables(t *testing.T) {
	const lan, other = 0xC0A80132, 0x0A000005 // 192.168.1.50, 10.0.0.5
	local := [4]byte{192, 168, 1, 50}
	for name, layout := range map[string]ownerRow{"tcp": tcpOwnerRow, "udp": udpOwnerRow} {
		table := ownerTable(layout,
			[3]uint32{other, 50000, 111}, // same port, different address
			[3]uint32{0, 50000, 222},     // wildcard bind
			[3]uint32{lan, 50000, 333},   // exact
			[3]uint32{0, 50001, 444},
		)
		if pid, ok := findOwner(table, layout, local, 50000); !ok || pid != 333 {
			t.Errorf("%s: exact match = %d %v, want 333", name, pid, ok)
		}
		if pid, ok := findOwner(table, layout, local, 50001); !ok || pid != 444 {
			t.Errorf("%s: wildcard match = %d %v, want 444", name, pid, ok)
		}
		if _, ok := findOwner(table, layout, local, 50002); ok {
			t.Errorf("%s: found an owner for an unused port", name)
		}
		// A count larger than the data must not read out of bounds.
		truncated := append(binary.LittleEndian.AppendUint32(nil, 1000), table[4:4+layout.size]...)
		if _, ok := findOwner(truncated, layout, local, 50001); ok {
			t.Errorf("%s: truncated table matched", name)
		}
	}
	if _, ok := findOwner(nil, tcpOwnerRow, local, 1); ok {
		t.Error("empty table matched")
	}
}

func TestFindOwnerOfIPv4SentThroughDualStackSocket(t *testing.T) {
	local := [4]byte{192, 168, 1, 50}
	row := func(layout ownerRow, addr [16]byte, port uint16, pid uint32) []byte {
		b := make([]byte, layout.size)
		copy(b[layout.addrAt:], addr[:])
		binary.BigEndian.PutUint16(b[layout.portAt:], port)
		binary.LittleEndian.PutUint32(b[layout.pidAt:], pid)
		return b
	}
	mapped := [16]byte{10: 0xff, 11: 0xff, 12: 192, 13: 168, 14: 1, 15: 50}
	otherMapped := [16]byte{10: 0xff, 11: 0xff, 12: 10, 13: 0, 14: 0, 15: 5}
	realV6 := [16]byte{0: 0x20, 1: 0x01, 15: 1}
	for name, layout := range map[string]ownerRow{"tcp6": tcp6OwnerRow, "udp6": udp6OwnerRow} {
		table := binary.LittleEndian.AppendUint32(nil, 5)
		table = append(table, row(layout, realV6, 50000, 111)...)      // a genuine IPv6 socket on the same port
		table = append(table, row(layout, otherMapped, 50000, 222)...) // mapped, but another address
		table = append(table, row(layout, [16]byte{}, 50000, 333)...)  // bound to ::
		table = append(table, row(layout, mapped, 50000, 444)...)      // exact
		table = append(table, row(layout, [16]byte{}, 50001, 555)...)
		if pid, ok := findOwnerDualStack(table, layout, local, 50000); !ok || pid != 444 {
			t.Errorf("%s: mapped match = %d %v, want 444", name, pid, ok)
		}
		if pid, ok := findOwnerDualStack(table, layout, local, 50001); !ok || pid != 555 {
			t.Errorf("%s: wildcard match = %d %v, want 555", name, pid, ok)
		}
		only := append(binary.LittleEndian.AppendUint32(nil, 2), row(layout, realV6, 50000, 111)...)
		only = append(only, row(layout, otherMapped, 50000, 222)...)
		if pid, ok := findOwnerDualStack(only, layout, local, 50000); ok {
			t.Errorf("%s: matched pid %d bound to a different address", name, pid)
		}
	}
}

type fakeTUN struct {
	written chan []byte
	closed  chan struct{}
	once    sync.Once
}

func (f *fakeTUN) Write(p []byte) (int, error) { f.written <- bytes.Clone(p); return len(p), nil }
func (f *fakeTUN) Read(p []byte) (int, error)  { <-f.closed; return 0, io.EOF }
func (f *fakeTUN) Close() error                { f.once.Do(func() { close(f.closed) }); return nil }

type fakeCapture struct {
	outbound   chan []byte
	reinjected chan []byte
	closed     chan struct{}
	once       sync.Once
}

func (c *fakeCapture) Recv(buf []byte) (int, Meta, error) {
	select {
	case pkt := <-c.outbound:
		return copy(buf, pkt), Meta{IfIdx: 3}, nil
	case <-c.closed:
		return 0, Meta{}, errors.New("closed")
	}
}
func (c *fakeCapture) Reinject(pkt []byte, _ Meta) error {
	c.reinjected <- bytes.Clone(pkt)
	return nil
}
func (c *fakeCapture) InjectInbound([]byte, Meta) error { return nil }
func (c *fakeCapture) Close() error                     { c.once.Do(func() { close(c.closed) }); return nil }

type owner struct {
	pid uint32
	exe string
}

type fakeResolver struct {
	mu     sync.Mutex
	owners map[uint16]owner
}

func (r *fakeResolver) set(port uint16, pid uint32, exe string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if exe == "" {
		delete(r.owners, port)
		return
	}
	r.owners[port] = owner{pid, exe}
}

func (r *fakeResolver) Owner(_ uint8, _ [4]byte, port uint16) (uint32, string, bool) {
	r.mu.Lock()
	defer r.mu.Unlock()
	o, ok := r.owners[port]
	return o.pid, o.exe, ok
}

const (
	gameExe    = `C:\Games\Shooter\shooter.exe`
	browserExe = `C:\Browser\browser.exe`
)

var (
	lanIP  = [4]byte{192, 168, 1, 50}
	gameIP = [4]byte{203, 0, 113, 9}
)

type rig struct {
	t        *testing.T
	engine   *Engine
	capture  *fakeCapture
	resolver *fakeResolver
	tun      *fakeTUN
	server   *relay.Server
	clock    atomic.Int64
}

func newRig(t *testing.T, startRelay bool) *rig {
	t.Helper()
	key, _ := proto.GenerateKey()
	secret := []byte("0123456789abcdef")
	conn, err := net.ListenUDP("udp4", &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1)})
	if err != nil {
		t.Fatal(err)
	}
	r := &rig{
		t:        t,
		capture:  &fakeCapture{outbound: make(chan []byte, 16), reinjected: make(chan []byte, 16), closed: make(chan struct{})},
		resolver: &fakeResolver{owners: map[uint16]owner{}},
		tun:      &fakeTUN{written: make(chan []byte, 16), closed: make(chan struct{})},
	}
	r.clock.Store(time.Now().UnixNano())
	r.server, err = relay.New(conn, r.tun, relay.Options{StaticKey: key, TokenSecret: secret, Pool: netip.MustParsePrefix("10.66.0.0/24")})
	if err != nil {
		t.Fatal(err)
	}
	if startRelay {
		go r.server.Serve()
	}
	t.Cleanup(r.server.Close)

	token, _ := proto.SignToken(secret, proto.Token{UserID: "u", Device: "d", Expires: time.Now().Add(time.Hour).Unix()})
	tunnel, err := NewTunnel(conn.LocalAddr().String(), base64.StdEncoding.EncodeToString(key.PublicKey().Bytes()), string(token))
	if err != nil {
		t.Fatal(err)
	}
	tunnel.pingEvery = 20 * time.Millisecond
	tunnel.deadAfter = 150 * time.Millisecond
	r.engine = New(r.capture, r.resolver, tunnel, []Rule{{Name: "Shooter", Dirs: []string{`C:\Games\Shooter`}}})
	r.engine.now = func() time.Time { return time.Unix(0, r.clock.Load()) }
	go r.engine.Run()
	t.Cleanup(r.engine.Close)
	if startRelay {
		r.waitConnected(true)
	}
	return r
}

func (r *rig) waitConnected(want bool) {
	r.t.Helper()
	deadline := time.Now().Add(3 * time.Second)
	for r.engine.Status().Tunnel.Connected != want {
		if time.Now().After(deadline) {
			r.t.Fatalf("tunnel connected never became %v", want)
		}
		time.Sleep(5 * time.Millisecond)
	}
}

func udp(srcPort uint16, payload string) []byte {
	b := make([]byte, 28+len(payload))
	b[0] = 0x45
	binary.BigEndian.PutUint16(b[2:4], uint16(len(b)))
	b[8], b[9] = 64, packet.ProtoUDP
	copy(b[12:16], lanIP[:])
	copy(b[16:20], gameIP[:])
	binary.BigEndian.PutUint16(b[20:22], srcPort)
	binary.BigEndian.PutUint16(b[22:24], 27015)
	binary.BigEndian.PutUint16(b[24:26], uint16(8+len(payload)))
	copy(b[28:], payload)
	return b
}

func tcp(srcPort uint16, flags uint8) []byte {
	b := make([]byte, 40)
	b[0] = 0x45
	binary.BigEndian.PutUint16(b[2:4], 40)
	b[8], b[9] = 64, packet.ProtoTCP
	copy(b[12:16], lanIP[:])
	copy(b[16:20], gameIP[:])
	binary.BigEndian.PutUint16(b[20:22], srcPort)
	binary.BigEndian.PutUint16(b[22:24], 443)
	b[32], b[33] = 5<<4, flags
	return b
}

// expectTunneled asserts the packet reached the relay's TUN device, carrying
// the client's tunnel address instead of its LAN address.
func (r *rig) expectTunneled(what string) {
	r.t.Helper()
	select {
	case pkt := <-r.tun.written:
		info, err := packet.Parse(pkt)
		if err != nil || info.Src != [4]byte{10, 66, 0, 2} || info.Dst != gameIP {
			r.t.Fatalf("%s reached the relay as %v -> %v (%v)", what, info.Src, info.Dst, err)
		}
	case pkt := <-r.capture.reinjected:
		r.t.Fatalf("%s went out directly instead of through the tunnel: % x", what, pkt[:20])
	case <-time.After(2 * time.Second):
		r.t.Fatalf("%s vanished: neither tunneled nor sent directly", what)
	}
}

func (r *rig) expectDirect(what string, original []byte) {
	r.t.Helper()
	select {
	case pkt := <-r.capture.reinjected:
		if !bytes.Equal(pkt, original) {
			r.t.Fatalf("%s was sent directly but modified", what)
		}
	case <-r.tun.written:
		r.t.Fatalf("%s was tunneled, want it sent directly", what)
	case <-time.After(2 * time.Second):
		r.t.Fatalf("%s vanished: neither tunneled nor sent directly", what)
	}
}

func (r *rig) expectDropped(what string) {
	r.t.Helper()
	select {
	case <-r.capture.reinjected:
		r.t.Fatalf("%s leaked out directly", what)
	case <-r.tun.written:
		r.t.Fatalf("%s was tunneled", what)
	case <-time.After(150 * time.Millisecond):
	}
}

func (r *rig) send(pkt []byte) { r.capture.outbound <- bytes.Clone(pkt) }

func TestTCPConnectionOpenedBeforeEngineStaysDirectButNewOnesAreTunneled(t *testing.T) {
	r := newRig(t, true)
	r.resolver.set(50001, 100, gameExe)

	// The game was already connected when boost was switched on: taking the
	// connection over mid-stream would make the far end see a new address.
	ack := tcp(50001, 0x10)
	r.send(ack)
	r.expectDirect("mid-stream TCP segment", ack)
	r.send(ack)
	r.expectDirect("later segment of the same old connection", ack)

	// The game reconnects from the same port: that is a new connection.
	r.send(tcp(50001, 0x02))
	r.expectTunneled("new TCP connection (SYN)")
	r.send(tcp(50001, 0x10))
	r.expectTunneled("follow-up segment of the new connection")
}

func TestConnectionStartedWhileTunnelDownStaysDirectAfterItComesUp(t *testing.T) {
	r := newRig(t, false) // relay not answering yet
	r.resolver.set(50000, 100, gameExe)

	first := udp(50000, "before tunnel")
	r.send(first)
	r.expectDirect("game packet while the tunnel is down", first)

	go r.server.Serve()
	r.waitConnected(true)
	r.clock.Add(int64(time.Minute)) // well past the owner re-check interval

	later := udp(50000, "after tunnel")
	r.send(later)
	r.expectDirect("same game connection after the tunnel came up", later)

	// A connection the game opens now does use the tunnel.
	r.resolver.set(50010, 100, gameExe)
	r.send(udp(50010, "new socket"))
	r.expectTunneled("new game connection")
}

func TestUDPPortReusedByAnotherProgramStopsBeingTunneled(t *testing.T) {
	r := newRig(t, true)
	r.resolver.set(50000, 100, gameExe)
	r.send(udp(50000, "game"))
	r.expectTunneled("game packet")

	// The game exits and a browser happens to get the same port.
	r.resolver.set(50000, 200, browserExe)
	r.send(udp(50000, "still cached"))
	r.expectTunneled("packet inside the re-check interval")

	r.clock.Add(int64(udpReverifyAfter + time.Second))
	browser := udp(50000, "browser")
	r.send(browser)
	r.expectDirect("another program's packet on the reused port", browser)
}

func TestOwnerUnknownAtFirstIsRetriedAndThenTunneled(t *testing.T) {
	r := newRig(t, true)
	first := udp(50000, "socket not in the table yet")
	r.send(first)
	r.expectDirect("packet with unknown owner", first)

	r.resolver.set(50000, 100, gameExe)
	r.clock.Add(int64(unresolvedRetryAfter + 50*time.Millisecond))
	r.send(udp(50000, "now known"))
	r.expectTunneled("game packet once its owner resolves")
}

func TestTunneledConnectionIsDroppedNotLeakedWhenRelayDies(t *testing.T) {
	r := newRig(t, true)
	r.resolver.set(50000, 100, gameExe)
	r.send(udp(50000, "game"))
	r.expectTunneled("game packet")

	r.server.Close()
	r.waitConnected(false)
	if status := r.engine.Status().Tunnel; status.Error == "" {
		t.Fatalf("a dead relay should be reported: %+v", status)
	}

	r.send(udp(50000, "relay is gone"))
	r.expectDropped("packet of an already-tunneled connection")
	if r.engine.Status().DroppedWhileDown == 0 {
		t.Fatal("dropped packet was not counted")
	}

	// The game's next connection works without boost rather than not at all.
	r.resolver.set(50020, 100, gameExe)
	fresh := udp(50020, "reconnect")
	r.send(fresh)
	r.expectDirect("new connection while the relay is down", fresh)
}

func TestControlAPI(t *testing.T) {
	var built atomic.Int32
	var rigs []*rig
	factory := func(cfg StartConfig) (*Engine, error) {
		if cfg.Relay == "fail:1" {
			return nil, errors.New("driver could not be opened")
		}
		built.Add(1)
		r := newRigWithoutRun(t)
		rigs = append(rigs, r)
		return r.engine, nil
	}
	controller := NewController(factory, "secret-key")
	server := httptest.NewServer(controller.Handler())
	defer server.Close()
	defer controller.Stop()

	call := func(method, path, key, body string) (int, map[string]any) {
		t.Helper()
		req, _ := http.NewRequest(method, server.URL+path, strings.NewReader(body))
		if key != "" {
			req.Header.Set("X-Nexora-Key", key)
		}
		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			t.Fatal(err)
		}
		defer resp.Body.Close()
		var decoded map[string]any
		json.NewDecoder(resp.Body).Decode(&decoded)
		return resp.StatusCode, decoded
	}

	if code, _ := call("GET", "/v1/status", "", ""); code != http.StatusUnauthorized {
		t.Fatalf("no key: %d", code)
	}
	if code, _ := call("GET", "/v1/status", "wrong", ""); code != http.StatusUnauthorized {
		t.Fatalf("wrong key: %d", code)
	}
	if code, body := call("GET", "/v1/status", "secret-key", ""); code != 200 || body["running"] != false {
		t.Fatalf("idle status: %d %v", code, body)
	}
	if code, _ := call("POST", "/v1/start", "secret-key", `{"relay":"x:1"}`); code != http.StatusBadRequest {
		t.Fatalf("incomplete config: %d", code)
	}
	if code, _ := call("POST", "/v1/start", "secret-key", `not json`); code != http.StatusBadRequest {
		t.Fatalf("bad json: %d", code)
	}
	good := `{"relay":"203.0.113.1:4700","relay_public_key":"k","token":"t","rules":[{"name":"G","exes":["g.exe"]}]}`
	if code, body := call("POST", "/v1/start", "secret-key", good); code != 200 || body["running"] != true {
		t.Fatalf("start: %d %v", code, body)
	}
	if code, body := call("GET", "/v1/status", "secret-key", ""); code != 200 || body["tunnel"] == nil || body["flows"] == nil {
		t.Fatalf("running status lacks tunnel/flows: %d %v", code, body)
	}
	// Starting again replaces the engine instead of leaking the old one.
	call("POST", "/v1/start", "secret-key", good)
	if built.Load() != 2 || !rigs[0].engine.closed.Load() {
		t.Fatalf("restart: built=%d first closed=%v", built.Load(), rigs[0].engine.closed.Load())
	}
	if code, body := call("POST", "/v1/stop", "secret-key", ""); code != 200 || body["running"] != false {
		t.Fatalf("stop: %d %v", code, body)
	}
	if !rigs[1].engine.closed.Load() {
		t.Fatal("stop did not close the engine")
	}
	failing := strings.Replace(good, "203.0.113.1:4700", "fail:1", 1)
	if code, body := call("POST", "/v1/start", "secret-key", failing); code != 500 || !strings.Contains(body["error"].(string), "driver") {
		t.Fatalf("factory failure: %d %v", code, body)
	}
	if _, body := call("GET", "/v1/status", "secret-key", ""); body["running"] != false || body["error"] == nil {
		t.Fatalf("status after failed start: %v", body)
	}
	if code, _ := call("POST", "/v1/probe", "secret-key", `{"relays":[]}`); code != http.StatusBadRequest {
		t.Fatalf("empty probe: %d", code)
	}
}

// newRigWithoutRun builds an engine the controller will run itself.
func newRigWithoutRun(t *testing.T) *rig {
	t.Helper()
	key, _ := proto.GenerateKey()
	tunnel, err := NewTunnel("127.0.0.1:9", base64.StdEncoding.EncodeToString(key.PublicKey().Bytes()), "token")
	if err != nil {
		t.Fatal(err)
	}
	r := &rig{
		t:        t,
		capture:  &fakeCapture{outbound: make(chan []byte, 1), reinjected: make(chan []byte, 1), closed: make(chan struct{})},
		resolver: &fakeResolver{owners: map[uint16]owner{}},
	}
	r.engine = New(r.capture, r.resolver, tunnel, nil)
	t.Cleanup(r.engine.Close)
	return r
}
