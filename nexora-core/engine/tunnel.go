package engine

import (
	"crypto/ecdh"
	"encoding/base64"
	"encoding/binary"
	"errors"
	"fmt"
	"net"
	"net/netip"
	"sort"
	"sync"
	"sync/atomic"
	"time"

	"nexora.app/core/proto"
)

const (
	pingInterval     = time.Second
	deadAfter        = 6 * time.Second
	helloRetry       = time.Second
	rejectedRetry    = 30 * time.Second
	tunnelReadBuffer = 4 << 20
)

type liveSession struct {
	crypto *proto.Session
	vip    [4]byte
}

// Tunnel is the encrypted UDP association with one relay. It reconnects on
// its own, and measures round-trip time and loss with its keepalives.
type Tunnel struct {
	conn     *net.UDPConn
	relay    netip.AddrPort
	relayKey *ecdh.PublicKey
	token    []byte
	onPacket func(inner []byte)
	now      func() time.Time
	// How often to ping, and how long without a pong means the relay is gone.
	pingEvery time.Duration
	deadAfter time.Duration

	session atomic.Pointer[liveSession]

	mu        sync.Mutex
	pending   *proto.ClientHandshake
	lastError string
	rejected  bool

	established chan struct{}
	lastPong    atomic.Int64
	rttMicros   atomic.Int64
	pingsSent   atomic.Uint64
	pongsSeen   atomic.Uint64
	bytesOut    atomic.Uint64
	bytesIn     atomic.Uint64

	closed atomic.Bool
	done   chan struct{}
}

// NewTunnel resolves the relay and opens the UDP socket; nothing is sent
// until Start. relayPublicKey is base64, as printed by `nexora-relay pubkey`.
func NewTunnel(relayAddr, relayPublicKey, token string) (*Tunnel, error) {
	rawKey, err := base64.StdEncoding.DecodeString(relayPublicKey)
	if err != nil {
		return nil, fmt.Errorf("relay public key: %w", err)
	}
	key, err := proto.ParsePublicKey(rawKey)
	if err != nil {
		return nil, fmt.Errorf("relay public key: %w", err)
	}
	udpAddr, err := net.ResolveUDPAddr("udp4", relayAddr)
	if err != nil {
		return nil, fmt.Errorf("relay address: %w", err)
	}
	relay := udpAddr.AddrPort()
	relay = netip.AddrPortFrom(relay.Addr().Unmap(), relay.Port())
	if !relay.Addr().Is4() {
		return nil, errors.New("relay address: IPv4 required")
	}
	conn, err := net.ListenUDP("udp4", nil)
	if err != nil {
		return nil, err
	}
	_ = conn.SetReadBuffer(tunnelReadBuffer)
	_ = conn.SetWriteBuffer(tunnelReadBuffer)
	return &Tunnel{
		conn:        conn,
		relay:       relay,
		relayKey:    key,
		token:       []byte(token),
		now:         time.Now,
		pingEvery:   pingInterval,
		deadAfter:   deadAfter,
		established: make(chan struct{}, 1),
		done:        make(chan struct{}),
	}, nil
}

func (t *Tunnel) RelayIP() [4]byte { return t.relay.Addr().As4() }

// VirtualIP is the address this client has on the relay while the tunnel is up.
func (t *Tunnel) VirtualIP() ([4]byte, bool) {
	if live := t.session.Load(); live != nil {
		return live.vip, true
	}
	return [4]byte{}, false
}

func (t *Tunnel) Start() {
	go t.readLoop()
	go t.keepLoop()
}

func (t *Tunnel) Close() {
	if t.closed.Swap(true) {
		return
	}
	if live := t.session.Load(); live != nil {
		t.conn.WriteToUDPAddrPort(live.crypto.Seal(nil, proto.TypeBye, nil), t.relay)
	}
	close(t.done)
	t.conn.Close()
}

// Send tunnels one inner IPv4 packet. It is a no-op while the tunnel is down.
func (t *Tunnel) Send(inner []byte) {
	live := t.session.Load()
	if live == nil {
		return
	}
	datagram := live.crypto.Seal(make([]byte, 0, len(inner)+proto.Overhead), proto.TypeData, inner)
	if _, err := t.conn.WriteToUDPAddrPort(datagram, t.relay); err == nil {
		t.bytesOut.Add(uint64(len(inner)))
	}
}

func (t *Tunnel) sendHello() {
	hs, hello, err := proto.NewClientHello(t.relayKey, t.token)
	if err != nil {
		return
	}
	t.mu.Lock()
	t.pending = hs
	t.mu.Unlock()
	t.conn.WriteToUDPAddrPort(hello, t.relay)
}

// keepLoop owns the connection state machine: handshake until up, ping while
// up, and declare the tunnel dead when the relay stops answering.
func (t *Tunnel) keepLoop() {
	var payload [8]byte
	for {
		if t.closed.Load() {
			return
		}
		live := t.session.Load()
		wait := t.pingEvery
		if live == nil {
			t.mu.Lock()
			rejected := t.rejected
			t.rejected = false
			t.mu.Unlock()
			if rejected {
				// A bad or expired token will not get better by hammering
				// the relay; the UI has to supply a new one.
				wait = rejectedRetry
			} else {
				t.sendHello()
				wait = helloRetry
			}
		} else {
			now := t.now()
			if now.UnixNano()-t.lastPong.Load() > int64(t.deadAfter) {
				t.session.CompareAndSwap(live, nil)
				t.setError("relay stopped responding")
				continue
			}
			binary.BigEndian.PutUint64(payload[:], uint64(now.UnixNano()))
			t.conn.WriteToUDPAddrPort(live.crypto.Seal(nil, proto.TypePing, payload[:]), t.relay)
			t.pingsSent.Add(1)
		}
		select {
		case <-t.done:
			return
		case <-t.established:
		case <-time.After(wait):
		}
	}
}

func (t *Tunnel) setError(message string) {
	t.mu.Lock()
	t.lastError = message
	t.mu.Unlock()
}

func (t *Tunnel) readLoop() {
	buf := make([]byte, 65535)
	plain := make([]byte, 0, 65535)
	for {
		n, from, err := t.conn.ReadFromUDPAddrPort(buf)
		if err != nil {
			if t.closed.Load() {
				return
			}
			continue
		}
		from = netip.AddrPortFrom(from.Addr().Unmap(), from.Port())
		if n == 0 || from != t.relay {
			continue
		}
		datagram := buf[:n]
		switch datagram[0] {
		case proto.TypeWelcome, proto.TypeReject:
			t.finishHandshake(datagram)
		default:
			live := t.session.Load()
			if live == nil {
				continue
			}
			typ, payload, err := live.crypto.Open(plain[:0], datagram)
			if err != nil {
				continue
			}
			switch typ {
			case proto.TypeData:
				t.bytesIn.Add(uint64(len(payload)))
				if t.onPacket != nil {
					t.onPacket(payload)
				}
			case proto.TypePong:
				if len(payload) == 8 {
					now := t.now().UnixNano()
					sent := int64(binary.BigEndian.Uint64(payload))
					if rtt := now - sent; rtt >= 0 {
						t.rttMicros.Store(rtt / 1000)
					}
					t.lastPong.Store(now)
					t.pongsSeen.Add(1)
				}
			}
		}
	}
}

func (t *Tunnel) finishHandshake(datagram []byte) {
	t.mu.Lock()
	hs := t.pending
	t.mu.Unlock()
	if hs == nil {
		return
	}
	crypto, welcome, err := hs.Finish(datagram)
	if err != nil {
		var rejected *proto.RejectError
		if errors.As(err, &rejected) {
			t.mu.Lock()
			t.pending = nil
			t.rejected = true
			t.lastError = rejected.Error()
			t.mu.Unlock()
		}
		return
	}
	t.mu.Lock()
	t.pending = nil
	t.lastError = ""
	t.mu.Unlock()
	t.lastPong.Store(t.now().UnixNano())
	t.session.Store(&liveSession{crypto: crypto, vip: welcome.VirtualIP})
	select {
	case t.established <- struct{}{}:
	default:
	}
}

// TunnelStatus is the tunnel half of the engine's status report.
type TunnelStatus struct {
	Connected bool    `json:"connected"`
	Relay     string  `json:"relay"`
	VirtualIP string  `json:"virtual_ip,omitempty"`
	RTTMs     float64 `json:"rtt_ms"`
	LossPct   float64 `json:"loss_percent"`
	BytesOut  uint64  `json:"bytes_out"`
	BytesIn   uint64  `json:"bytes_in"`
	Error     string  `json:"error,omitempty"`
}

func (t *Tunnel) Status() TunnelStatus {
	status := TunnelStatus{
		Relay:    t.relay.String(),
		BytesOut: t.bytesOut.Load(),
		BytesIn:  t.bytesIn.Load(),
	}
	if live := t.session.Load(); live != nil {
		status.Connected = true
		status.VirtualIP = netip.AddrFrom4(live.vip).String()
		status.RTTMs = float64(t.rttMicros.Load()) / 1000
	}
	if sent := t.pingsSent.Load(); sent > 0 {
		// The newest ping may simply still be in flight.
		seen := min(t.pongsSeen.Load()+1, sent)
		status.LossPct = 100 * float64(sent-seen) / float64(sent)
	}
	t.mu.Lock()
	status.Error = t.lastError
	t.mu.Unlock()
	return status
}

// ProbeResult is one relay's measured round-trip time.
type ProbeResult struct {
	Relay string  `json:"relay"`
	OK    bool    `json:"ok"`
	RTTMs float64 `json:"rtt_ms"`
	Lost  int     `json:"lost"`
}

// Probe measures round-trip time to each relay without opening a session,
// so the UI can pick the best server before connecting. Results come back
// fastest first, unreachable relays last.
func Probe(relays []string, attempts int, timeout time.Duration) []ProbeResult {
	results := make([]ProbeResult, len(relays))
	var wg sync.WaitGroup
	for i, relay := range relays {
		wg.Add(1)
		go func() {
			defer wg.Done()
			results[i] = probeOne(relay, attempts, timeout)
		}()
	}
	wg.Wait()
	sort.SliceStable(results, func(i, j int) bool {
		if results[i].OK != results[j].OK {
			return results[i].OK
		}
		return results[i].RTTMs < results[j].RTTMs
	})
	return results
}

func probeOne(relay string, attempts int, timeout time.Duration) ProbeResult {
	result := ProbeResult{Relay: relay, Lost: attempts}
	conn, err := net.Dial("udp4", relay)
	if err != nil {
		return result
	}
	defer conn.Close()

	var samples []time.Duration
	msg := make([]byte, proto.ProbeLen)
	reply := make([]byte, 64)
	msg[0] = proto.TypeProbe
	for i := range attempts {
		binary.BigEndian.PutUint64(msg[1:], uint64(time.Now().UnixNano())+uint64(i))
		sent := time.Now()
		if _, err := conn.Write(msg); err != nil {
			continue
		}
		conn.SetReadDeadline(sent.Add(timeout))
		for {
			n, err := conn.Read(reply)
			if err != nil {
				break
			}
			if n == proto.ProbeLen && reply[0] == proto.TypeProbeReply && string(reply[1:n]) == string(msg[1:]) {
				samples = append(samples, time.Since(sent))
				break
			}
		}
	}
	if len(samples) == 0 {
		return result
	}
	sort.Slice(samples, func(i, j int) bool { return samples[i] < samples[j] })
	result.OK = true
	result.Lost = attempts - len(samples)
	result.RTTMs = float64(samples[len(samples)/2].Microseconds()) / 1000
	return result
}
