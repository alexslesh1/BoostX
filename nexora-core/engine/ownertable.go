package engine

import "encoding/binary"

// ownerRow describes one of Windows' IP Helper "owner PID" table layouts.
type ownerRow struct {
	size, addrAt, portAt, pidAt int
}

var (
	// MIB_TCPROW_OWNER_PID: state, localAddr, localPort, remoteAddr, remotePort, pid.
	tcpOwnerRow = ownerRow{size: 24, addrAt: 4, portAt: 8, pidAt: 20}
	// MIB_UDPROW_OWNER_PID: localAddr, localPort, pid.
	udpOwnerRow = ownerRow{size: 12, addrAt: 0, portAt: 4, pidAt: 8}
)

// findOwner looks a local endpoint up in a raw owner table: a little-endian
// row count followed by fixed-size rows. An exact address match wins over a
// socket bound to 0.0.0.0, which sends from whichever address routing picks
// and therefore matches any.
func findOwner(table []byte, layout ownerRow, localAddr [4]byte, localPort uint16) (uint32, bool) {
	if len(table) < 4 {
		return 0, false
	}
	count := int(binary.LittleEndian.Uint32(table[0:4]))
	rows := table[4:]
	var wildcardPID uint32
	wildcardFound := false
	for i := 0; i < count && (i+1)*layout.size <= len(rows); i++ {
		row := rows[i*layout.size : (i+1)*layout.size]
		// Ports are stored in network byte order in the low 16 bits.
		if binary.BigEndian.Uint16(row[layout.portAt:layout.portAt+2]) != localPort {
			continue
		}
		pid := binary.LittleEndian.Uint32(row[layout.pidAt : layout.pidAt+4])
		addr := [4]byte(row[layout.addrAt : layout.addrAt+4])
		if addr == localAddr {
			return pid, true
		}
		if addr == [4]byte{} && !wildcardFound {
			wildcardPID, wildcardFound = pid, true
		}
	}
	return wildcardPID, wildcardFound
}

var (
	// MIB_TCP6ROW_OWNER_PID: localAddr[16], scope, localPort, remoteAddr[16], scope, remotePort, state, pid.
	tcp6OwnerRow = ownerRow{size: 56, addrAt: 0, portAt: 20, pidAt: 52}
	// MIB_UDP6ROW_OWNER_PID: localAddr[16], scope, localPort, pid.
	udp6OwnerRow = ownerRow{size: 28, addrAt: 0, portAt: 20, pidAt: 24}
)

// findOwnerDualStack looks an IPv4 endpoint up in an IPv6 owner table.
// Many programs open one "dual-stack" IPv6 socket and send IPv4 through it;
// such a socket is listed only in the IPv6 table, bound to :: or to the
// IPv4-mapped form of the local address (::ffff:a.b.c.d).
func findOwnerDualStack(table []byte, layout ownerRow, localAddr [4]byte, localPort uint16) (uint32, bool) {
	if len(table) < 4 {
		return 0, false
	}
	count := int(binary.LittleEndian.Uint32(table[0:4]))
	rows := table[4:]
	mapped := [16]byte{10: 0xff, 11: 0xff, 12: localAddr[0], 13: localAddr[1], 14: localAddr[2], 15: localAddr[3]}
	var wildcardPID uint32
	wildcardFound := false
	for i := 0; i < count && (i+1)*layout.size <= len(rows); i++ {
		row := rows[i*layout.size : (i+1)*layout.size]
		if binary.BigEndian.Uint16(row[layout.portAt:layout.portAt+2]) != localPort {
			continue
		}
		pid := binary.LittleEndian.Uint32(row[layout.pidAt : layout.pidAt+4])
		addr := [16]byte(row[layout.addrAt : layout.addrAt+16])
		if addr == mapped {
			return pid, true
		}
		if addr == [16]byte{} && !wildcardFound {
			wildcardPID, wildcardFound = pid, true
		}
	}
	return wildcardPID, wildcardFound
}
