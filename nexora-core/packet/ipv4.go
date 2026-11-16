// Package packet rewrites raw IPv4 packets in place: the address translation,
// checksum repair, MSS clamping and splitting that the engine needs to move a
// process's traffic into the tunnel and back. It has no OS dependencies.
package packet

import (
	"encoding/binary"
	"errors"
)

const (
	ProtoICMP = 1
	ProtoTCP  = 6
	ProtoUDP  = 17

	tcpFIN = 0x01
	tcpSYN = 0x02
	tcpPSH = 0x08
	tcpACK = 0x10
	tcpCWR = 0x80

	flagDF  = 0x4000
	flagMF  = 0x2000
	offMask = 0x1FFF
)

var (
	ErrNotIPv4   = errors.New("packet: not IPv4")
	ErrTruncated = errors.New("packet: truncated")
)

// Info is the handful of header fields the engine and relay route on.
type Info struct {
	HeaderLen int
	TotalLen  int
	Proto     uint8
	Src, Dst  [4]byte
	ID        uint16
	DontFrag  bool
	// FirstFragment is true for unfragmented packets too: it means the
	// transport header is present, so ports are valid.
	FirstFragment bool
	Fragmented    bool
	SrcPort       uint16
	DstPort       uint16
	TCPFlags      uint8
	L4Offset      int
}

// Normalize repairs the IPv4 total-length field from the real buffer length.
// Windows hands out segmentation-offloaded sends whose header length field
// is zero or stale; everything downstream trusts the header.
func Normalize(b []byte) {
	if len(b) >= 20 && b[0]>>4 == 4 && len(b) <= 0xFFFF {
		if int(binary.BigEndian.Uint16(b[2:4])) != len(b) {
			binary.BigEndian.PutUint16(b[2:4], uint16(len(b)))
		}
	}
}

// Parse validates an IPv4 packet and extracts routing fields.
func Parse(b []byte) (Info, error) {
	var info Info
	if len(b) < 20 || b[0]>>4 != 4 {
		return info, ErrNotIPv4
	}
	ihl := int(b[0]&0x0F) * 4
	total := int(binary.BigEndian.Uint16(b[2:4]))
	if ihl < 20 || total < ihl || total > len(b) {
		return info, ErrTruncated
	}
	fragField := binary.BigEndian.Uint16(b[6:8])
	info.HeaderLen = ihl
	info.TotalLen = total
	info.Proto = b[9]
	copy(info.Src[:], b[12:16])
	copy(info.Dst[:], b[16:20])
	info.ID = binary.BigEndian.Uint16(b[4:6])
	info.DontFrag = fragField&flagDF != 0
	info.FirstFragment = fragField&offMask == 0
	info.Fragmented = fragField&flagMF != 0 || fragField&offMask != 0
	info.L4Offset = ihl
	if !info.FirstFragment {
		return info, nil
	}
	l4 := b[ihl:total]
	switch info.Proto {
	case ProtoTCP:
		if len(l4) < 20 {
			return info, ErrTruncated
		}
		info.SrcPort = binary.BigEndian.Uint16(l4[0:2])
		info.DstPort = binary.BigEndian.Uint16(l4[2:4])
		info.TCPFlags = l4[13]
	case ProtoUDP:
		if len(l4) < 8 {
			return info, ErrTruncated
		}
		info.SrcPort = binary.BigEndian.Uint16(l4[0:2])
		info.DstPort = binary.BigEndian.Uint16(l4[2:4])
	}
	return info, nil
}

// IsSYN reports a TCP connection-opening segment (SYN without ACK).
func (i Info) IsSYN() bool {
	return i.Proto == ProtoTCP && i.TCPFlags&tcpSYN != 0 && i.TCPFlags&tcpACK == 0
}

func sum16(b []byte, sum uint32) uint32 {
	for len(b) >= 2 {
		sum += uint32(b[0])<<8 | uint32(b[1])
		b = b[2:]
	}
	if len(b) == 1 {
		sum += uint32(b[0]) << 8
	}
	return sum
}

func fold(sum uint32) uint16 {
	for sum>>16 != 0 {
		sum = sum&0xFFFF + sum>>16
	}
	return ^uint16(sum)
}

func fixIPChecksum(b []byte, ihl int) {
	b[10], b[11] = 0, 0
	binary.BigEndian.PutUint16(b[10:12], fold(sum16(b[:ihl], 0)))
}

func l4ChecksumOffset(proto uint8) int {
	switch proto {
	case ProtoTCP:
		return 16
	case ProtoUDP:
		return 6
	}
	return -1
}

// FixChecksums recomputes the IP header checksum and, for unfragmented TCP
// and UDP, the full transport checksum. A full recompute (rather than an
// incremental patch) is deliberate: packets captured on Windows often carry
// only a partial checksum because the NIC was meant to finish it.
func FixChecksums(b []byte) error {
	info, err := Parse(b)
	if err != nil {
		return err
	}
	b = b[:info.TotalLen]
	fixIPChecksum(b, info.HeaderLen)
	off := l4ChecksumOffset(info.Proto)
	if off < 0 || info.Fragmented {
		return nil
	}
	l4 := b[info.HeaderLen:]
	if len(l4) < off+2 {
		return ErrTruncated
	}
	l4[off], l4[off+1] = 0, 0
	sum := sum16(b[12:20], 0)
	sum += uint32(info.Proto) + uint32(len(l4))
	check := fold(sum16(l4, sum))
	if info.Proto == ProtoUDP && check == 0 {
		check = 0xFFFF
	}
	binary.BigEndian.PutUint16(l4[off:off+2], check)
	return nil
}

// patchL4ForAddr applies RFC 1624 to a first fragment's transport checksum,
// which covers the whole datagram and so can't be recomputed from one piece.
func patchL4ForAddr(b []byte, info Info, old, new [4]byte) {
	off := l4ChecksumOffset(info.Proto)
	if off < 0 || !info.FirstFragment {
		return
	}
	l4 := b[info.HeaderLen:info.TotalLen]
	if len(l4) < off+2 {
		return
	}
	check := binary.BigEndian.Uint16(l4[off : off+2])
	if info.Proto == ProtoUDP && check == 0 {
		return
	}
	sum := uint32(^check)
	sum += uint32(^binary.BigEndian.Uint16(old[0:2])) + uint32(^binary.BigEndian.Uint16(old[2:4]))
	sum += uint32(binary.BigEndian.Uint16(new[0:2])) + uint32(binary.BigEndian.Uint16(new[2:4]))
	check = fold(sum)
	if info.Proto == ProtoUDP && check == 0 {
		check = 0xFFFF
	}
	binary.BigEndian.PutUint16(l4[off:off+2], check)
}

func rewriteAddr(b []byte, at int, addr [4]byte) error {
	info, err := Parse(b)
	if err != nil {
		return err
	}
	var old [4]byte
	copy(old[:], b[at:at+4])
	copy(b[at:at+4], addr[:])
	if info.Fragmented {
		patchL4ForAddr(b, info, old, addr)
		fixIPChecksum(b, info.HeaderLen)
		return nil
	}
	return FixChecksums(b)
}

// RewriteSrc replaces the source address and repairs every checksum.
func RewriteSrc(b []byte, addr [4]byte) error { return rewriteAddr(b, 12, addr) }

// RewriteDst replaces the destination address and repairs every checksum.
func RewriteDst(b []byte, addr [4]byte) error { return rewriteAddr(b, 16, addr) }

// ClampMSS lowers the MSS option of a TCP SYN or SYN-ACK to at most mss, so
// neither end ever sends a segment that won't fit the tunnel. The caller
// must repair checksums afterwards. It reports whether anything changed.
func ClampMSS(b []byte, mss uint16) bool {
	info, err := Parse(b)
	if err != nil || info.Proto != ProtoTCP || !info.FirstFragment || info.TCPFlags&tcpSYN == 0 {
		return false
	}
	tcp := b[info.HeaderLen:info.TotalLen]
	dataOff := int(tcp[12]>>4) * 4
	if dataOff < 20 || dataOff > len(tcp) {
		return false
	}
	opts := tcp[20:dataOff]
	for i := 0; i < len(opts); {
		switch opts[i] {
		case 0:
			return false
		case 1:
			i++
			continue
		}
		if i+1 >= len(opts) {
			return false
		}
		size := int(opts[i+1])
		if size < 2 || i+size > len(opts) {
			return false
		}
		if opts[i] == 2 && size == 4 {
			if binary.BigEndian.Uint16(opts[i+2:i+4]) > mss {
				binary.BigEndian.PutUint16(opts[i+2:i+4], mss)
				return true
			}
			return false
		}
		i += size
	}
	return false
}

// SegmentTCP splits one oversized TCP segment into several that each fit
// maxLen bytes of IP packet. Windows hands the engine pre-segmentation
// "giant" sends when the NIC offers large-send offload; inside the tunnel
// there is no NIC to finish that job. Returns nil if b already fits.
func SegmentTCP(b []byte, maxLen int) ([][]byte, error) {
	info, err := Parse(b)
	if err != nil {
		return nil, err
	}
	if info.Proto != ProtoTCP || info.Fragmented || info.TotalLen <= maxLen {
		return nil, nil
	}
	b = b[:info.TotalLen]
	tcp := b[info.HeaderLen:]
	dataOff := int(tcp[12]>>4) * 4
	if dataOff < 20 || dataOff > len(tcp) {
		return nil, ErrTruncated
	}
	headers := info.HeaderLen + dataOff
	chunk := maxLen - headers
	if chunk <= 0 {
		return nil, ErrTruncated
	}
	payload := tcp[dataOff:]
	seq := binary.BigEndian.Uint32(tcp[4:8])
	flags := tcp[13]

	var out [][]byte
	for off := 0; off < len(payload); off += chunk {
		end := min(off+chunk, len(payload))
		first, last := off == 0, end == len(payload)
		seg := make([]byte, headers+end-off)
		copy(seg, b[:headers])
		copy(seg[headers:], payload[off:end])

		binary.BigEndian.PutUint16(seg[2:4], uint16(len(seg)))
		binary.BigEndian.PutUint16(seg[4:6], info.ID+uint16(len(out)))
		segTCP := seg[info.HeaderLen:]
		binary.BigEndian.PutUint32(segTCP[4:8], seq+uint32(off))
		segFlags := flags
		if !last {
			segFlags &^= tcpFIN | tcpPSH
		}
		if !first {
			segFlags &^= tcpCWR
		}
		segTCP[13] = segFlags
		if err := FixChecksums(seg); err != nil {
			return nil, err
		}
		out = append(out, seg)
	}
	return out, nil
}

// FragmentIPv4 splits a non-TCP packet that exceeds mtu into IP fragments.
// It returns nil if b already fits, and ErrDontFragment if the sender
// forbade fragmentation (the caller drops it, which is what a real path
// with a smaller MTU would do).
func FragmentIPv4(b []byte, mtu int) ([][]byte, error) {
	info, err := Parse(b)
	if err != nil {
		return nil, err
	}
	if info.TotalLen <= mtu {
		return nil, nil
	}
	if info.DontFrag {
		return nil, ErrDontFragment
	}
	b = b[:info.TotalLen]
	ihl := info.HeaderLen
	chunk := (mtu - ihl) &^ 7
	if chunk <= 0 {
		return nil, ErrTruncated
	}
	origField := binary.BigEndian.Uint16(b[6:8])
	baseOff := int(origField&offMask) * 8
	moreAfter := origField&flagMF != 0
	payload := b[ihl:]

	var out [][]byte
	for off := 0; off < len(payload); off += chunk {
		end := min(off+chunk, len(payload))
		frag := make([]byte, ihl+end-off)
		copy(frag, b[:ihl])
		copy(frag[ihl:], payload[off:end])
		binary.BigEndian.PutUint16(frag[2:4], uint16(len(frag)))
		field := uint16((baseOff + off) / 8)
		if end < len(payload) || moreAfter {
			field |= flagMF
		}
		binary.BigEndian.PutUint16(frag[6:8], field)
		fixIPChecksum(frag, ihl)
		out = append(out, frag)
	}
	return out, nil
}

var ErrDontFragment = errors.New("packet: too big and DF set")

// IsTunnelable reports whether dst is a public unicast address. Traffic to
// the LAN, loopback, multicast and broadcast must stay on the local network:
// the relay couldn't deliver it, and the relay must never be usable to reach
// its own private network either.
func IsTunnelable(dst [4]byte) bool {
	switch {
	case dst[0] == 0, dst[0] == 10, dst[0] == 127:
		return false
	case dst[0] == 100 && dst[1]&0xC0 == 64: // 100.64/10 carrier-grade NAT
		return false
	case dst[0] == 169 && dst[1] == 254:
		return false
	case dst[0] == 172 && dst[1]&0xF0 == 16:
		return false
	case dst[0] == 192 && dst[1] == 168:
		return false
	case dst[0] >= 224: // multicast, reserved, broadcast
		return false
	}
	return true
}
