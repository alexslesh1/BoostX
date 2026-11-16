//go:build windows

package engine

import (
	"sync"
	"time"
	"unsafe"

	"golang.org/x/sys/windows"

	"nexora.app/core/packet"
)

const (
	afInet               = 2
	afInet6              = 23
	tcpTableOwnerPIDAll  = 5
	udpTableOwnerPID     = 1
	ownerLookupAttempts  = 3
	ownerLookupRetryWait = time.Millisecond
	exePathCacheFor      = 5 * time.Second
)

var (
	iphlpapi                = windows.NewLazySystemDLL("iphlpapi.dll")
	procGetExtendedTcpTable = iphlpapi.NewProc("GetExtendedTcpTable")
	procGetExtendedUdpTable = iphlpapi.NewProc("GetExtendedUdpTable")
)

type cachedExe struct {
	path    string
	expires time.Time
}

// WindowsResolver answers "which program owns this local port" from the
// system's own socket tables. Because the engine is holding the packet in
// question while it asks, the socket is guaranteed to exist already: there
// is no race between a connection opening and the engine learning about it.
type WindowsResolver struct {
	mu   sync.Mutex
	exes map[uint32]cachedExe
	buf  []byte
}

func NewResolver() *WindowsResolver {
	return &WindowsResolver{exes: map[uint32]cachedExe{}, buf: make([]byte, 64<<10)}
}

func (r *WindowsResolver) Owner(protocol uint8, localAddr [4]byte, localPort uint16) (uint32, string, bool) {
	r.mu.Lock()
	defer r.mu.Unlock()
	for attempt := range ownerLookupAttempts {
		if attempt > 0 {
			time.Sleep(ownerLookupRetryWait)
		}
		pid, ok := r.ownerPID(protocol, localAddr, localPort)
		if ok {
			return pid, r.exePath(pid), true
		}
	}
	return 0, "", false
}

// table fills r.buf with one of the IP Helper owner tables and returns it.
func (r *WindowsResolver) table(proc *windows.LazyProc, family, class uintptr) []byte {
	for range 4 {
		size := uint32(len(r.buf))
		ret, _, _ := proc.Call(uintptr(unsafe.Pointer(&r.buf[0])), uintptr(unsafe.Pointer(&size)), 0, family, class, 0)
		switch windows.Errno(ret) {
		case 0:
			return r.buf[:size]
		case windows.ERROR_INSUFFICIENT_BUFFER:
			r.buf = make([]byte, size+16<<10)
		default:
			return nil
		}
	}
	return nil
}

func (r *WindowsResolver) ownerPID(protocol uint8, localAddr [4]byte, localPort uint16) (uint32, bool) {
	proc, class, v4, v6 := procGetExtendedUdpTable, uintptr(udpTableOwnerPID), udpOwnerRow, udp6OwnerRow
	if protocol == packet.ProtoTCP {
		proc, class, v4, v6 = procGetExtendedTcpTable, tcpTableOwnerPIDAll, tcpOwnerRow, tcp6OwnerRow
	}
	if pid, ok := findOwner(r.table(proc, afInet, class), v4, localAddr, localPort); ok {
		return pid, true
	}
	// IPv4 sent through a dual-stack IPv6 socket is listed only there.
	return findOwnerDualStack(r.table(proc, afInet6, class), v6, localAddr, localPort)
}

func (r *WindowsResolver) exePath(pid uint32) string {
	now := time.Now()
	if cached, ok := r.exes[pid]; ok && now.Before(cached.expires) {
		return cached.path
	}
	path := queryExePath(pid)
	if len(r.exes) > 4096 {
		clear(r.exes)
	}
	r.exes[pid] = cachedExe{path: path, expires: now.Add(exePathCacheFor)}
	return path
}

func queryExePath(pid uint32) string {
	handle, err := windows.OpenProcess(windows.PROCESS_QUERY_LIMITED_INFORMATION, false, pid)
	if err != nil {
		return ""
	}
	defer windows.CloseHandle(handle)
	buf := make([]uint16, windows.MAX_LONG_PATH)
	size := uint32(len(buf))
	if err := windows.QueryFullProcessImageName(handle, 0, &buf[0], &size); err != nil {
		return ""
	}
	return windows.UTF16ToString(buf[:size])
}
