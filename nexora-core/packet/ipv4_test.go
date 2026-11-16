package packet

import (
	"bytes"
	"encoding/binary"
	"errors"
	"testing"
)

// buildIPv4 assembles a packet with deliberately wrong checksums, the way a
// checksum-offloaded capture looks, so tests prove FixChecksums really ran.
func buildIPv4(proto uint8, src, dst [4]byte, l4 []byte, flagsFrag uint16) []byte {
	b := make([]byte, 20+len(l4))
	b[0] = 0x45
	binary.BigEndian.PutUint16(b[2:4], uint16(len(b)))
	binary.BigEndian.PutUint16(b[4:6], 0x1234)
	binary.BigEndian.PutUint16(b[6:8], flagsFrag)
	b[8] = 64
	b[9] = proto
	copy(b[12:16], src[:])
	copy(b[16:20], dst[:])
	copy(b[20:], l4)
	return b
}

func udpSegment(srcPort, dstPort uint16, payload []byte) []byte {
	l4 := make([]byte, 8+len(payload))
	binary.BigEndian.PutUint16(l4[0:2], srcPort)
	binary.BigEndian.PutUint16(l4[2:4], dstPort)
	binary.BigEndian.PutUint16(l4[4:6], uint16(len(l4)))
	binary.BigEndian.PutUint16(l4[6:8], 0xBEEF)
	copy(l4[8:], payload)
	return l4
}

func tcpSegment(srcPort, dstPort uint16, seq uint32, flags uint8, options, payload []byte) []byte {
	l4 := make([]byte, 20+len(options)+len(payload))
	binary.BigEndian.PutUint16(l4[0:2], srcPort)
	binary.BigEndian.PutUint16(l4[2:4], dstPort)
	binary.BigEndian.PutUint32(l4[4:8], seq)
	l4[12] = uint8((20+len(options))/4) << 4
	l4[13] = flags
	binary.BigEndian.PutUint16(l4[14:16], 65535)
	binary.BigEndian.PutUint16(l4[16:18], 0xDEAD)
	copy(l4[20:], options)
	copy(l4[20+len(options):], payload)
	return l4
}

// checksumsValid verifies the way a receiving stack does: summing a region
// together with its stored checksum must give all-ones.
func checksumsValid(t *testing.T, b []byte) {
	t.Helper()
	info, err := Parse(b)
	if err != nil {
		t.Fatalf("Parse: %v", err)
	}
	if fold(sum16(b[:info.HeaderLen], 0)) != 0 {
		t.Fatalf("IP header checksum invalid")
	}
	if info.Proto != ProtoTCP && info.Proto != ProtoUDP {
		return
	}
	l4 := b[info.HeaderLen:info.TotalLen]
	sum := sum16(b[12:20], 0) + uint32(info.Proto) + uint32(len(l4))
	if fold(sum16(l4, sum)) != 0 {
		t.Fatalf("transport checksum invalid")
	}
}

var (
	lan    = [4]byte{192, 168, 1, 50}
	vip    = [4]byte{10, 66, 0, 2}
	server = [4]byte{203, 0, 113, 9}
)

func TestFixChecksumsRepairsOffloadedTCPAndUDP(t *testing.T) {
	udp := buildIPv4(ProtoUDP, lan, server, udpSegment(50000, 27015, []byte("game state")), 0)
	if err := FixChecksums(udp); err != nil {
		t.Fatal(err)
	}
	checksumsValid(t, udp)

	tcp := buildIPv4(ProtoTCP, lan, server, tcpSegment(50001, 443, 1000, tcpACK|tcpPSH, nil, []byte("odd")), flagDF)
	if err := FixChecksums(tcp); err != nil {
		t.Fatal(err)
	}
	checksumsValid(t, tcp)
}

func TestRewriteSrcAndDstKeepPacketsValid(t *testing.T) {
	b := buildIPv4(ProtoUDP, lan, server, udpSegment(50000, 27015, []byte("hello")), 0)
	if err := RewriteSrc(b, vip); err != nil {
		t.Fatal(err)
	}
	info, _ := Parse(b)
	if info.Src != vip || info.Dst != server || info.SrcPort != 50000 || info.DstPort != 27015 {
		t.Fatalf("after RewriteSrc: %+v", info)
	}
	checksumsValid(t, b)

	reply := buildIPv4(ProtoTCP, server, vip, tcpSegment(443, 50001, 77, tcpACK, nil, []byte("reply")), 0)
	if err := RewriteDst(reply, lan); err != nil {
		t.Fatal(err)
	}
	info, _ = Parse(reply)
	if info.Dst != lan || info.Src != server {
		t.Fatalf("after RewriteDst: %+v", info)
	}
	checksumsValid(t, reply)
}

func TestFragmentThenRewriteReassemblesToAValidDatagram(t *testing.T) {
	payload := bytes.Repeat([]byte{0xA5, 0x5A, 0x01}, 1000)
	whole := buildIPv4(ProtoUDP, lan, server, udpSegment(50000, 27015, payload), 0)
	if err := FixChecksums(whole); err != nil {
		t.Fatal(err)
	}

	frags, err := FragmentIPv4(whole, 1400)
	if err != nil {
		t.Fatal(err)
	}
	if len(frags) != 3 {
		t.Fatalf("got %d fragments, want 3", len(frags))
	}

	var reassembled []byte
	for i, frag := range frags {
		if len(frag) > 1400 {
			t.Fatalf("fragment %d is %d bytes", i, len(frag))
		}
		// The engine rewrites each fragment separately; only the first
		// carries the UDP header, yet the datagram must stay valid.
		if err := RewriteSrc(frag, vip); err != nil {
			t.Fatal(err)
		}
		info, _ := Parse(frag)
		if fold(sum16(frag[:info.HeaderLen], 0)) != 0 {
			t.Fatalf("fragment %d IP checksum invalid", i)
		}
		if info.FirstFragment != (i == 0) || !info.Fragmented {
			t.Fatalf("fragment %d flags wrong: %+v", i, info)
		}
		field := binary.BigEndian.Uint16(frag[6:8])
		if (field&flagMF != 0) != (i < len(frags)-1) {
			t.Fatalf("fragment %d MF bit wrong", i)
		}
		if int(field&offMask)*8 != len(reassembled) {
			t.Fatalf("fragment %d offset %d, want %d", i, int(field&offMask)*8, len(reassembled))
		}
		reassembled = append(reassembled, frag[info.HeaderLen:]...)
	}

	rebuilt := buildIPv4(ProtoUDP, vip, server, reassembled, 0)
	fixIPChecksum(rebuilt, 20)
	checksumsValid(t, rebuilt)
	if !bytes.Equal(rebuilt[28:], payload) {
		t.Fatal("payload corrupted by fragmentation")
	}
}

func TestFragmentIPv4RespectsDontFragmentAndSmallPackets(t *testing.T) {
	small := buildIPv4(ProtoUDP, lan, server, udpSegment(1, 2, []byte("x")), 0)
	if frags, err := FragmentIPv4(small, 1400); frags != nil || err != nil {
		t.Fatalf("small packet: %v %v", frags, err)
	}
	big := buildIPv4(ProtoUDP, lan, server, udpSegment(1, 2, make([]byte, 2000)), flagDF)
	if _, err := FragmentIPv4(big, 1400); !errors.Is(err, ErrDontFragment) {
		t.Fatalf("DF err = %v", err)
	}
}

func TestClampMSS(t *testing.T) {
	options := []byte{1, 1, 2, 4, 0x05, 0xB4, 4, 2} // NOP NOP MSS=1460 SACK-permitted
	syn := buildIPv4(ProtoTCP, lan, server, tcpSegment(50001, 443, 1, tcpSYN, options, nil), flagDF)
	if !ClampMSS(syn, 1360) {
		t.Fatal("SYN with MSS 1460 was not clamped")
	}
	if got := binary.BigEndian.Uint16(syn[20+20+4 : 20+20+6]); got != 1360 {
		t.Fatalf("MSS = %d, want 1360", got)
	}
	if ClampMSS(syn, 1360) {
		t.Fatal("already-small MSS reported as changed")
	}

	notSyn := buildIPv4(ProtoTCP, lan, server, tcpSegment(50001, 443, 1, tcpACK, options, nil), flagDF)
	if ClampMSS(notSyn, 1360) {
		t.Fatal("non-SYN segment was modified")
	}
	synAck := buildIPv4(ProtoTCP, server, vip, tcpSegment(443, 50001, 1, tcpSYN|tcpACK, options, nil), flagDF)
	if !ClampMSS(synAck, 1360) {
		t.Fatal("SYN-ACK was not clamped")
	}
	truncatedOption := buildIPv4(ProtoTCP, lan, server, tcpSegment(1, 2, 1, tcpSYN, []byte{2, 9, 0, 0}, nil), 0)
	if ClampMSS(truncatedOption, 1360) {
		t.Fatal("malformed option list was modified")
	}
}

func TestSegmentTCPSplitsGiantSendCorrectly(t *testing.T) {
	payload := make([]byte, 5000)
	for i := range payload {
		payload[i] = byte(i * 7)
	}
	const seq = 0xFFFFF000 // wraps mid-way, like a real long-lived connection
	giant := buildIPv4(ProtoTCP, vip, server, tcpSegment(50001, 443, seq, tcpACK|tcpPSH|tcpFIN|tcpCWR, nil, payload), flagDF)

	segments, err := SegmentTCP(giant, 1400)
	if err != nil {
		t.Fatal(err)
	}
	if len(segments) != 4 {
		t.Fatalf("got %d segments, want 4", len(segments))
	}
	var joined []byte
	for i, seg := range segments {
		if len(seg) > 1400 {
			t.Fatalf("segment %d is %d bytes", i, len(seg))
		}
		checksumsValid(t, seg)
		tcp := seg[20:]
		if got := binary.BigEndian.Uint32(tcp[4:8]); got != seq+uint32(len(joined)) {
			t.Fatalf("segment %d seq = %#x, want %#x", i, got, seq+uint32(len(joined)))
		}
		last := i == len(segments)-1
		if hasFinPsh := tcp[13]&(tcpFIN|tcpPSH) == tcpFIN|tcpPSH; hasFinPsh != last {
			t.Fatalf("segment %d FIN/PSH = %v, want only on the last", i, hasFinPsh)
		}
		if hasCWR := tcp[13]&tcpCWR != 0; hasCWR != (i == 0) {
			t.Fatalf("segment %d CWR = %v, want only on the first", i, hasCWR)
		}
		if tcp[13]&tcpACK == 0 {
			t.Fatalf("segment %d lost ACK", i)
		}
		joined = append(joined, tcp[20:]...)
	}
	if !bytes.Equal(joined, payload) {
		t.Fatal("payload corrupted by segmentation")
	}

	small := buildIPv4(ProtoTCP, vip, server, tcpSegment(1, 2, 1, tcpACK, nil, []byte("fits")), 0)
	if segs, err := SegmentTCP(small, 1400); segs != nil || err != nil {
		t.Fatalf("small segment: %v %v", segs, err)
	}
}

func TestNormalizeRepairsZeroTotalLength(t *testing.T) {
	b := buildIPv4(ProtoTCP, lan, server, tcpSegment(1, 2, 1, tcpACK, nil, make([]byte, 3000)), 0)
	binary.BigEndian.PutUint16(b[2:4], 0)
	if _, err := Parse(b); err == nil {
		t.Fatal("expected Parse to reject a zero total length")
	}
	Normalize(b)
	info, err := Parse(b)
	if err != nil || info.TotalLen != len(b) {
		t.Fatalf("after Normalize: %+v %v", info, err)
	}
}

func TestParseRejectsGarbageAndReadsFragments(t *testing.T) {
	if _, err := Parse([]byte{0x60, 0, 0, 0}); !errors.Is(err, ErrNotIPv4) {
		t.Fatalf("IPv6/short err = %v", err)
	}
	truncated := buildIPv4(ProtoTCP, lan, server, []byte{1, 2, 3}, 0)
	if _, err := Parse(truncated); !errors.Is(err, ErrTruncated) {
		t.Fatalf("truncated TCP err = %v", err)
	}
	later := buildIPv4(ProtoUDP, lan, server, []byte{9, 9, 9, 9, 9, 9, 9, 9}, 185)
	info, err := Parse(later)
	if err != nil || info.FirstFragment || !info.Fragmented || info.SrcPort != 0 {
		t.Fatalf("non-first fragment: %+v %v", info, err)
	}
}

func TestIsTunnelable(t *testing.T) {
	cases := map[[4]byte]bool{
		{203, 0, 113, 9}:     true,
		{8, 8, 8, 8}:         true,
		{172, 32, 0, 1}:      true,
		{100, 128, 0, 1}:     true,
		{10, 0, 0, 5}:        false,
		{192, 168, 1, 1}:     false,
		{172, 16, 5, 5}:      false,
		{172, 31, 255, 255}:  false,
		{100, 64, 0, 1}:      false,
		{127, 0, 0, 1}:       false,
		{169, 254, 1, 1}:     false,
		{224, 0, 0, 251}:     false,
		{255, 255, 255, 255}: false,
		{0, 0, 0, 0}:         false,
	}
	for addr, want := range cases {
		if got := IsTunnelable(addr); got != want {
			t.Errorf("IsTunnelable(%v) = %v, want %v", addr, got, want)
		}
	}
}
