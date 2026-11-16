// Package engine is the client side of the Nexora tunnel. It takes the
// outbound packets of selected processes off the normal network path, sends
// them through a relay instead, and delivers the replies back to those
// processes — per application, with no virtual adapter and no change to the
// system routing table. Everything else on the machine is untouched.
//
// The OS-specific parts (capturing packets, finding which process owns a
// socket) sit behind the Capture and Resolver interfaces, so this file is
// the same code on every platform and is tested end to end on Linux.
package engine

import (
	"net/netip"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"nexora.app/core/packet"
	"nexora.app/core/proto"
)

const (
	clampedMSS = proto.InnerMTU - 40 - 20
	// A UDP port can be closed and reused by a different program, so its
	// owner is re-checked this often. TCP is re-checked on every SYN.
	udpReverifyAfter = 3 * time.Second
	// An unresolved owner is retried quickly: the lookup can lose a race
	// with a socket that is still being set up.
	unresolvedRetryAfter = 200 * time.Millisecond
	udpIdleTimeout       = 2 * time.Minute
	tcpIdleTimeout       = 10 * time.Minute
	fragmentTimeout      = 10 * time.Second
	sweepInterval        = 10 * time.Second
)

// Meta is where a packet was captured, which is also where its replies have
// to be injected.
type Meta struct {
	IfIdx    uint32
	SubIfIdx uint32
	// Flags is the capture driver's own per-packet flag word, handed back
	// unchanged when a packet is reinjected on its original path.
	Flags uint32
}

// Capture intercepts outbound packets before they leave the machine.
type Capture interface {
	// Recv blocks for the next outbound IPv4 TCP or UDP packet.
	Recv(buf []byte) (n int, meta Meta, err error)
	// Reinject puts a captured packet back on its original path, unchanged.
	Reinject(pkt []byte, meta Meta) error
	// InjectInbound delivers pkt to the local network stack as if it had
	// just arrived on meta's interface. Checksums are already valid.
	InjectInbound(pkt []byte, meta Meta) error
	Close() error
}

// Resolver finds the program that owns a local socket.
type Resolver interface {
	Owner(protocol uint8, localAddr [4]byte, localPort uint16) (pid uint32, exePath string, ok bool)
}

// Rule selects the programs whose traffic goes through the tunnel.
type Rule struct {
	Name string `json:"name"`
	// Exes are executable file names, e.g. "RobloxPlayerBeta.exe".
	Exes []string `json:"exes"`
	// Dirs are install directories: every program under one matches, which
	// covers launchers, anti-cheat and helper processes without listing them.
	Dirs []string `json:"dirs"`
}

type ruleSet struct {
	byExe map[string]string
	dirs  []dirRule
}

type dirRule struct {
	prefix string
	name   string
}

func normalizePath(path string) string {
	return strings.ToLower(strings.ReplaceAll(path, "/", `\`))
}

func newRuleSet(rules []Rule) *ruleSet {
	set := &ruleSet{byExe: map[string]string{}}
	for _, rule := range rules {
		for _, exe := range rule.Exes {
			set.byExe[strings.ToLower(exe)] = rule.Name
		}
		for _, dir := range rule.Dirs {
			prefix := strings.TrimRight(normalizePath(dir), `\`) + `\`
			if prefix != `\` {
				set.dirs = append(set.dirs, dirRule{prefix: prefix, name: rule.Name})
			}
		}
	}
	return set
}

func (s *ruleSet) match(exePath string) string {
	normalized := normalizePath(exePath)
	base := normalized
	if i := strings.LastIndexByte(normalized, '\\'); i >= 0 {
		base = normalized[i+1:]
	}
	if name, ok := s.byExe[base]; ok {
		return name
	}
	for _, dir := range s.dirs {
		if strings.HasPrefix(normalized, dir.prefix) {
			return dir.name
		}
	}
	return ""
}

type flowKey struct {
	proto uint8
	port  uint16
}

type flow struct {
	tunneled bool
	resolved bool
	rule     string
	pid      uint32
	exe      string
	localIP  [4]byte
	meta     Meta
	remote   netip.AddrPort
	created  time.Time
	verified time.Time
	lastSeen time.Time
	bytesOut uint64
	bytesIn  uint64
}

type fragKey struct {
	peer [4]byte
	id   uint16
}

type fragEntry struct {
	key  flowKey
	seen time.Time
}

// Engine moves the selected programs' traffic through one relay.
type Engine struct {
	capture  Capture
	resolver Resolver
	tunnel   *Tunnel
	rules    *ruleSet
	relayIP  [4]byte
	now      func() time.Time

	mu      sync.Mutex
	flows   map[flowKey]*flow
	fragOut map[fragKey]fragEntry
	fragIn  map[fragKey]fragEntry

	droppedDown atomic.Uint64
	closed      atomic.Bool
	done        chan struct{}
}

// New wires an engine together. The tunnel must not be started yet.
func New(capture Capture, resolver Resolver, tunnel *Tunnel, rules []Rule) *Engine {
	e := &Engine{
		capture:  capture,
		resolver: resolver,
		tunnel:   tunnel,
		rules:    newRuleSet(rules),
		relayIP:  tunnel.RelayIP(),
		now:      time.Now,
		flows:    map[flowKey]*flow{},
		fragOut:  map[fragKey]fragEntry{},
		fragIn:   map[fragKey]fragEntry{},
		done:     make(chan struct{}),
	}
	tunnel.onPacket = e.handleInbound
	return e
}

// Run captures until Close. It returns the capture error that ended it.
func (e *Engine) Run() error {
	e.tunnel.Start()
	go e.sweepLoop()
	buf := make([]byte, 0xFFFF+64)
	for {
		n, meta, err := e.capture.Recv(buf)
		if err != nil {
			if e.closed.Load() {
				return nil
			}
			e.Close()
			return err
		}
		e.handleOutbound(buf[:n], meta)
	}
}

func (e *Engine) Close() {
	if e.closed.Swap(true) {
		return
	}
	close(e.done)
	e.tunnel.Close()
	e.capture.Close()
}

func (e *Engine) handleOutbound(pkt []byte, meta Meta) {
	packet.Normalize(pkt)
	info, err := packet.Parse(pkt)
	if err != nil || (info.Proto != packet.ProtoTCP && info.Proto != packet.ProtoUDP) ||
		!packet.IsTunnelable(info.Dst) || info.Dst == e.relayIP {
		e.capture.Reinject(pkt, meta)
		return
	}
	pkt = pkt[:info.TotalLen]
	now := e.now()

	e.mu.Lock()
	var f *flow
	if info.FirstFragment {
		f = e.classifyLocked(info, meta, now)
		if info.Fragmented {
			e.fragOut[fragKey{peer: info.Dst, id: info.ID}] = fragEntry{key: flowKey{info.Proto, info.SrcPort}, seen: now}
		}
	} else if entry, ok := e.fragOut[fragKey{peer: info.Dst, id: info.ID}]; ok {
		f = e.flows[entry.key]
	}
	tunneled := f != nil && f.tunneled
	if tunneled {
		f.lastSeen = now
		f.bytesOut += uint64(len(pkt))
		f.meta = meta
	}
	e.mu.Unlock()

	if !tunneled {
		e.capture.Reinject(pkt, meta)
		return
	}
	vip, up := e.tunnel.VirtualIP()
	if !up {
		// This connection already lives on the relay's address; letting it
		// leak out directly would only confuse the far end. New connections
		// made while the tunnel is down go direct instead (see classify).
		e.droppedDown.Add(1)
		return
	}

	packet.ClampMSS(pkt, clampedMSS)
	if packet.RewriteSrc(pkt, vip) != nil {
		return
	}
	var pieces [][]byte
	if info.Proto == packet.ProtoTCP {
		pieces, err = packet.SegmentTCP(pkt, clampedMSS+40)
	} else {
		pieces, err = packet.FragmentIPv4(pkt, proto.InnerMTU)
	}
	if err != nil {
		return
	}
	if pieces == nil {
		e.tunnel.Send(pkt)
		return
	}
	for _, piece := range pieces {
		e.tunnel.Send(piece)
	}
}

// classifyLocked decides, once per connection, whether it is tunneled.
func (e *Engine) classifyLocked(info packet.Info, meta Meta, now time.Time) *flow {
	key := flowKey{info.Proto, info.SrcPort}
	f := e.flows[key]

	recheck := f == nil || info.IsSYN()
	if !recheck && info.Proto == packet.ProtoUDP {
		after := udpReverifyAfter
		if !f.resolved {
			after = unresolvedRetryAfter
		}
		recheck = now.Sub(f.verified) > after
	}
	if !recheck {
		return f
	}

	pid, exe, ok := e.resolver.Owner(info.Proto, info.Src, info.SrcPort)
	if f != nil && !info.IsSYN() {
		if !ok || (f.resolved && f.pid == pid) {
			// Same owner, or a lookup that failed this time: a connection
			// never changes path mid-way, whatever the tunnel is doing now.
			f.verified = now
			return f
		}
	}

	fresh := &flow{
		resolved: ok,
		pid:      pid,
		exe:      exe,
		localIP:  info.Src,
		meta:     meta,
		remote:   netip.AddrPortFrom(netip.AddrFrom4(info.Dst), info.DstPort),
		created:  now,
		verified: now,
		lastSeen: now,
	}
	if ok {
		fresh.rule = e.rules.match(exe)
	}
	// A TCP connection first seen mid-stream was opened before the engine
	// started; moving it now would break it, so it stays direct.
	midStreamTCP := info.Proto == packet.ProtoTCP && !info.IsSYN()
	_, up := e.tunnel.VirtualIP()
	fresh.tunneled = fresh.rule != "" && up && !midStreamTCP
	e.flows[key] = fresh
	return fresh
}

func (e *Engine) handleInbound(pkt []byte) {
	info, err := packet.Parse(pkt)
	if err != nil || (info.Proto != packet.ProtoTCP && info.Proto != packet.ProtoUDP) {
		return
	}
	vip, up := e.tunnel.VirtualIP()
	if !up || info.Dst != vip {
		return
	}
	pkt = pkt[:info.TotalLen]
	now := e.now()

	e.mu.Lock()
	var key flowKey
	found := true
	if info.FirstFragment {
		key = flowKey{info.Proto, info.DstPort}
		if info.Fragmented {
			e.fragIn[fragKey{peer: info.Src, id: info.ID}] = fragEntry{key: key, seen: now}
		}
	} else {
		var entry fragEntry
		entry, found = e.fragIn[fragKey{peer: info.Src, id: info.ID}]
		key = entry.key
	}
	f := e.flows[key]
	if !found || f == nil || !f.tunneled {
		e.mu.Unlock()
		return
	}
	f.lastSeen = now
	f.bytesIn += uint64(len(pkt))
	localIP, meta := f.localIP, Meta{IfIdx: f.meta.IfIdx, SubIfIdx: f.meta.SubIfIdx}
	e.mu.Unlock()

	packet.ClampMSS(pkt, clampedMSS)
	if packet.RewriteDst(pkt, localIP) != nil {
		return
	}
	e.capture.InjectInbound(pkt, meta)
}

func (e *Engine) sweepLoop() {
	ticker := time.NewTicker(sweepInterval)
	defer ticker.Stop()
	for {
		select {
		case <-e.done:
			return
		case <-ticker.C:
			e.sweep(e.now())
		}
	}
}

func (e *Engine) sweep(now time.Time) {
	e.mu.Lock()
	defer e.mu.Unlock()
	for key, f := range e.flows {
		timeout := udpIdleTimeout
		if key.proto == packet.ProtoTCP {
			timeout = tcpIdleTimeout
		}
		if now.Sub(f.lastSeen) > timeout {
			delete(e.flows, key)
		}
	}
	for key, entry := range e.fragOut {
		if now.Sub(entry.seen) > fragmentTimeout {
			delete(e.fragOut, key)
		}
	}
	for key, entry := range e.fragIn {
		if now.Sub(entry.seen) > fragmentTimeout {
			delete(e.fragIn, key)
		}
	}
}

// FlowStatus is one tunneled connection, for the UI's connections table.
type FlowStatus struct {
	App       string `json:"app"`
	Exe       string `json:"exe"`
	PID       uint32 `json:"pid"`
	Protocol  string `json:"protocol"`
	LocalPort uint16 `json:"local_port"`
	Remote    string `json:"remote"`
	BytesOut  uint64 `json:"bytes_out"`
	BytesIn   uint64 `json:"bytes_in"`
	AgeSec    int64  `json:"age_seconds"`
}

// Status is a point-in-time view of the engine.
type Status struct {
	Tunnel            TunnelStatus `json:"tunnel"`
	Flows             []FlowStatus `json:"flows"`
	DroppedWhileDown  uint64       `json:"dropped_while_down"`
	TrackedSocketsAll int          `json:"tracked_sockets"`
}

func (e *Engine) Status() Status {
	now := e.now()
	status := Status{Tunnel: e.tunnel.Status(), DroppedWhileDown: e.droppedDown.Load(), Flows: []FlowStatus{}}
	e.mu.Lock()
	status.TrackedSocketsAll = len(e.flows)
	for key, f := range e.flows {
		if !f.tunneled {
			continue
		}
		protocol := "UDP"
		if key.proto == packet.ProtoTCP {
			protocol = "TCP"
		}
		status.Flows = append(status.Flows, FlowStatus{
			App:       f.rule,
			Exe:       filepath.Base(strings.ReplaceAll(f.exe, `\`, "/")),
			PID:       f.pid,
			Protocol:  protocol,
			LocalPort: key.port,
			Remote:    f.remote.String(),
			BytesOut:  f.bytesOut,
			BytesIn:   f.bytesIn,
			AgeSec:    int64(now.Sub(f.created) / time.Second),
		})
	}
	e.mu.Unlock()
	sort.Slice(status.Flows, func(i, j int) bool {
		a, b := status.Flows[i], status.Flows[j]
		if a.App != b.App {
			return a.App < b.App
		}
		return a.LocalPort < b.LocalPort
	})
	return status
}
