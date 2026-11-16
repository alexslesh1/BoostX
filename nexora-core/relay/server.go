// Package relay is the Nexora relay server: it terminates the tunnel from
// many clients and hands their raw IP packets to a TUN device, where the
// Linux kernel does the NAT towards game servers. The relay itself keeps no
// per-connection state and never calls the backend, so adding capacity is
// just starting the same binary on another machine.
package relay

import (
	"crypto/ecdh"
	"crypto/rand"
	"encoding/binary"
	"errors"
	"io"
	"log/slog"
	"net"
	"net/netip"
	"sync"
	"sync/atomic"
	"time"

	"nexora.app/core/packet"
	"nexora.app/core/proto"
)

const (
	// clampedMSS leaves room for 20-byte IP and 20-byte TCP headers plus
	// common TCP options inside proto.InnerMTU.
	clampedMSS     = proto.InnerMTU - 40 - 20
	reapInterval   = 15 * time.Second
	udpBufferBytes = 4 << 20
)

// Options configures a Server. TUN is anything packets can be read from and
// written to, so tests can substitute a pipe for the real device.
type Options struct {
	StaticKey   *ecdh.PrivateKey
	TokenSecret []byte
	Pool        netip.Prefix
	IdleTimeout time.Duration
	MaxSessions int
	Logger      *slog.Logger
	Now         func() time.Time
}

type session struct {
	crypto   *proto.Session
	vip      [4]byte
	owner    string
	helloEph [32]byte
	welcome  []byte

	endpoint atomic.Pointer[netip.AddrPort]
	lastSeen atomic.Int64
}

// Server relays between one UDP socket and one TUN device.
type Server struct {
	opts Options
	conn *net.UDPConn
	tun  io.ReadWriteCloser
	log  *slog.Logger

	mu      sync.RWMutex
	byID    map[uint64]*session
	byVIP   map[[4]byte]*session
	byOwner map[string]*session
	pool    *addrPool

	closed atomic.Bool
	done   chan struct{}
}

func New(conn *net.UDPConn, tun io.ReadWriteCloser, opts Options) (*Server, error) {
	if opts.StaticKey == nil || len(opts.TokenSecret) == 0 {
		return nil, errors.New("relay: static key and token secret are required")
	}
	pool, err := newAddrPool(opts.Pool)
	if err != nil {
		return nil, err
	}
	if opts.IdleTimeout <= 0 {
		opts.IdleTimeout = 3 * time.Minute
	}
	if opts.MaxSessions <= 0 {
		opts.MaxSessions = pool.capacity()
	}
	if opts.Logger == nil {
		opts.Logger = slog.Default()
	}
	if opts.Now == nil {
		opts.Now = time.Now
	}
	_ = conn.SetReadBuffer(udpBufferBytes)
	_ = conn.SetWriteBuffer(udpBufferBytes)
	return &Server{
		opts:    opts,
		conn:    conn,
		tun:     tun,
		log:     opts.Logger,
		byID:    map[uint64]*session{},
		byVIP:   map[[4]byte]*session{},
		byOwner: map[string]*session{},
		pool:    pool,
		done:    make(chan struct{}),
	}, nil
}

// Serve runs until Close; it returns the first fatal I/O error.
func (s *Server) Serve() error {
	errs := make(chan error, 2)
	go func() { errs <- s.udpLoop() }()
	go func() { errs <- s.tunLoop() }()
	go s.reapLoop()
	err := <-errs
	s.Close()
	if s.closed.Load() && err != nil && errors.Is(err, net.ErrClosed) {
		return nil
	}
	return err
}

func (s *Server) Close() {
	if s.closed.Swap(true) {
		return
	}
	close(s.done)
	s.conn.Close()
	s.tun.Close()
}

// SessionCount is the number of live sessions.
func (s *Server) SessionCount() int {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return len(s.byID)
}

func (s *Server) udpLoop() error {
	buf := make([]byte, 65535)
	plain := make([]byte, 0, 65535)
	out := make([]byte, 0, 2048)
	for {
		n, from, err := s.conn.ReadFromUDPAddrPort(buf)
		if err != nil {
			if s.closed.Load() {
				return net.ErrClosed
			}
			return err
		}
		datagram := buf[:n]
		if n == 0 {
			continue
		}
		switch datagram[0] {
		case proto.TypeProbe:
			// Same size out as in: useless for traffic amplification.
			if n == proto.ProbeLen {
				reply := append(out[:0], proto.TypeProbeReply)
				reply = append(reply, datagram[1:]...)
				s.conn.WriteToUDPAddrPort(reply, from)
			}
		case proto.TypeHello:
			s.handleHello(datagram, from)
		default:
			s.handleTransport(datagram, from, plain[:0], out[:0])
		}
	}
}

func (s *Server) handleHello(datagram []byte, from netip.AddrPort) {
	hello, err := proto.OpenHello(s.opts.StaticKey, datagram)
	if err != nil {
		return
	}
	token, err := proto.VerifyToken(s.opts.TokenSecret, hello.Token, s.opts.Now())
	if err != nil {
		code := proto.RejectBadToken
		if errors.Is(err, proto.ErrTokenExpired) {
			code = proto.RejectExpired
		}
		s.conn.WriteToUDPAddrPort(hello.Reject(code), from)
		return
	}
	owner := token.UserID + "/" + token.Device
	var eph [32]byte
	copy(eph[:], hello.ClientEph.Bytes())

	s.mu.Lock()
	existing := s.byOwner[owner]
	if existing != nil && existing.helloEph == eph {
		// A retransmitted HELLO: the first WELCOME was lost. Answering with
		// a fresh session would orphan a client that did get the first one.
		welcome := existing.welcome
		s.mu.Unlock()
		s.conn.WriteToUDPAddrPort(welcome, from)
		return
	}

	var vip [4]byte
	if existing != nil {
		// Same user and device reconnecting: keep the address so the
		// kernel's NAT entries, and the game's connections, survive.
		vip = existing.vip
	} else {
		ok := len(s.byID) < s.opts.MaxSessions
		if ok {
			vip, ok = s.pool.take()
		}
		if !ok {
			s.mu.Unlock()
			s.conn.WriteToUDPAddrPort(hello.Reject(proto.RejectFull), from)
			return
		}
	}

	id := s.newSessionIDLocked()
	crypto, welcome, err := hello.Accept(s.opts.StaticKey, proto.Welcome{
		SessionID:   id,
		VirtualIP:   vip,
		MTU:         proto.InnerMTU,
		IdleSeconds: uint16(s.opts.IdleTimeout / time.Second),
	})
	if err != nil {
		if existing == nil {
			s.pool.give(vip)
		}
		s.mu.Unlock()
		return
	}
	if existing != nil {
		delete(s.byID, existing.crypto.ID)
	}
	sess := &session{crypto: crypto, vip: vip, owner: owner, helloEph: eph, welcome: welcome}
	sess.endpoint.Store(&from)
	sess.lastSeen.Store(s.opts.Now().UnixNano())
	s.byID[id] = sess
	s.byVIP[vip] = sess
	s.byOwner[owner] = sess
	count := len(s.byID)
	s.mu.Unlock()

	s.conn.WriteToUDPAddrPort(welcome, from)
	s.log.Info("session opened", "user", token.UserID, "device", token.Device,
		"vip", netip.AddrFrom4(vip), "resumed", existing != nil, "sessions", count)
}

func (s *Server) newSessionIDLocked() uint64 {
	var raw [8]byte
	for {
		rand.Read(raw[:])
		id := binary.BigEndian.Uint64(raw[:])
		if _, taken := s.byID[id]; !taken && id != 0 {
			return id
		}
	}
}

func (s *Server) handleTransport(datagram []byte, from netip.AddrPort, plain, out []byte) {
	id, ok := proto.PeekSessionID(datagram)
	if !ok {
		return
	}
	s.mu.RLock()
	sess := s.byID[id]
	s.mu.RUnlock()
	if sess == nil {
		return
	}
	typ, payload, err := sess.crypto.Open(plain, datagram)
	if err != nil {
		return
	}
	// Only an authenticated datagram may move the session to a new address
	// (a client switching Wi-Fi to mobile, or a NAT rebinding its port).
	if current := sess.endpoint.Load(); current == nil || *current != from {
		sess.endpoint.Store(&from)
	}
	sess.lastSeen.Store(s.opts.Now().UnixNano())

	switch typ {
	case proto.TypeData:
		s.forwardToInternet(sess, payload)
	case proto.TypePing:
		s.conn.WriteToUDPAddrPort(sess.crypto.Seal(out, proto.TypePong, payload), from)
	case proto.TypeBye:
		s.removeSession(sess, "client closed")
	}
}

func (s *Server) forwardToInternet(sess *session, pkt []byte) {
	if len(pkt) > proto.InnerMTU {
		return
	}
	info, err := packet.Parse(pkt)
	if err != nil {
		return
	}
	pkt = pkt[:info.TotalLen]
	// Anti-spoofing and containment: a client may only send as its own
	// virtual address, and only to public addresses.
	if info.Src != sess.vip || !packet.IsTunnelable(info.Dst) {
		return
	}
	switch info.Proto {
	case packet.ProtoTCP, packet.ProtoUDP, packet.ProtoICMP:
	default:
		return
	}
	if packet.ClampMSS(pkt, clampedMSS) {
		if packet.FixChecksums(pkt) != nil {
			return
		}
	}
	s.tun.Write(pkt)
}

func (s *Server) tunLoop() error {
	buf := make([]byte, 65535)
	out := make([]byte, 0, 2048)
	for {
		n, err := s.tun.Read(buf)
		if err != nil {
			if s.closed.Load() {
				return net.ErrClosed
			}
			return err
		}
		pkt := buf[:n]
		info, err := packet.Parse(pkt)
		if err != nil || info.TotalLen > proto.InnerMTU {
			continue
		}
		pkt = pkt[:info.TotalLen]
		s.mu.RLock()
		sess := s.byVIP[info.Dst]
		s.mu.RUnlock()
		if sess == nil {
			continue
		}
		endpoint := sess.endpoint.Load()
		if endpoint == nil {
			continue
		}
		if packet.ClampMSS(pkt, clampedMSS) {
			if packet.FixChecksums(pkt) != nil {
				continue
			}
		}
		s.conn.WriteToUDPAddrPort(sess.crypto.Seal(out[:0], proto.TypeData, pkt), *endpoint)
	}
}

func (s *Server) removeSession(sess *session, reason string) {
	s.mu.Lock()
	if s.byID[sess.crypto.ID] != sess {
		s.mu.Unlock()
		return
	}
	delete(s.byID, sess.crypto.ID)
	delete(s.byVIP, sess.vip)
	delete(s.byOwner, sess.owner)
	s.pool.give(sess.vip)
	count := len(s.byID)
	s.mu.Unlock()
	s.log.Info("session closed", "vip", netip.AddrFrom4(sess.vip), "reason", reason, "sessions", count)
}

func (s *Server) reapLoop() {
	ticker := time.NewTicker(reapInterval)
	defer ticker.Stop()
	for {
		select {
		case <-s.done:
			return
		case <-ticker.C:
			s.reapIdle()
		}
	}
}

func (s *Server) reapIdle() {
	cutoff := s.opts.Now().Add(-s.opts.IdleTimeout).UnixNano()
	s.mu.RLock()
	var idle []*session
	for _, sess := range s.byID {
		if sess.lastSeen.Load() < cutoff {
			idle = append(idle, sess)
		}
	}
	s.mu.RUnlock()
	for _, sess := range idle {
		s.removeSession(sess, "idle")
	}
}

// addrPool hands out client addresses from the tunnel subnet. The network
// address, the gateway (first host, owned by the TUN device) and the
// broadcast address are never handed out.
type addrPool struct {
	base  uint32
	size  uint32
	next  uint32
	freed []uint32
}

func newAddrPool(prefix netip.Prefix) (*addrPool, error) {
	if !prefix.IsValid() || !prefix.Addr().Is4() || prefix.Bits() > 29 || prefix.Bits() < 8 {
		return nil, errors.New("relay: pool must be an IPv4 prefix between /8 and /29")
	}
	base := binary.BigEndian.Uint32(prefix.Masked().Addr().AsSlice())
	return &addrPool{base: base, size: 1 << (32 - prefix.Bits()), next: 2}, nil
}

func (p *addrPool) capacity() int { return int(p.size) - 3 }

func (p *addrPool) take() ([4]byte, bool) {
	var addr [4]byte
	var offset uint32
	switch {
	case len(p.freed) > 0:
		offset = p.freed[len(p.freed)-1]
		p.freed = p.freed[:len(p.freed)-1]
	case p.next < p.size-1:
		offset = p.next
		p.next++
	default:
		return addr, false
	}
	binary.BigEndian.PutUint32(addr[:], p.base+offset)
	return addr, true
}

func (p *addrPool) give(addr [4]byte) {
	p.freed = append(p.freed, binary.BigEndian.Uint32(addr[:])-p.base)
}

// GatewayAddr is the address the TUN device itself must be given.
func GatewayAddr(prefix netip.Prefix) netip.Addr {
	return prefix.Masked().Addr().Next()
}
