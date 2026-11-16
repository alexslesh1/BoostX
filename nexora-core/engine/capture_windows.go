//go:build windows

package engine

import (
	"errors"
	"fmt"
	"net/netip"
	"os"
	"path/filepath"
	"sync"
	"unsafe"

	"golang.org/x/sys/windows"
)

// WinDivert constants (windivert.h, version 2.x).
const (
	wdLayerNetwork = 0

	wdParamQueueLength = 0
	wdParamQueueTime   = 1
	wdParamQueueSize   = 2

	wdShutdownBoth = 3

	// Bits of WINDIVERT_ADDRESS's flag word: Layer:8, Event:8, then one bit each.
	wdFlagOutbound    = 1 << 17
	wdFlagIPChecksum  = 1 << 21
	wdFlagTCPChecksum = 1 << 22
	wdFlagUDPChecksum = 1 << 23
)

// wdAddress mirrors WINDIVERT_ADDRESS: 80 bytes, with the network layer's
// interface indexes at the start of the 64-byte union.
type wdAddress struct {
	Timestamp int64
	Flags     uint32
	Reserved2 uint32
	IfIdx     uint32
	SubIfIdx  uint32
	_         [56]byte
}

type winDivert struct {
	handle    windows.Handle
	recv      *windows.LazyProc
	send      *windows.LazyProc
	shutdown  *windows.LazyProc
	close     *windows.LazyProc
	closeOnce sync.Once
}

// findWinDivert locates the driver DLL beside the executable. It is loaded
// by absolute path only, never through the DLL search order, because this
// process runs elevated.
func findWinDivert() (string, error) {
	exe, err := os.Executable()
	if err != nil {
		return "", err
	}
	dir := filepath.Dir(exe)
	for _, name := range []string{"WinDivert.dll", "WinDivert64.dll"} {
		path := filepath.Join(dir, name)
		if _, err := os.Stat(path); err == nil {
			return path, nil
		}
	}
	return "", fmt.Errorf("WinDivert.dll not found next to %s (WinDivert64.sys must be there too)", exe)
}

// OpenCapture starts intercepting every outbound IPv4 TCP and UDP packet
// except loopback traffic and the tunnel's own packets to the relay.
// It requires administrator rights: opening WinDivert loads a kernel driver.
func OpenCapture(relayIP netip.Addr) (Capture, error) {
	dllPath, err := findWinDivert()
	if err != nil {
		return nil, err
	}
	dll := windows.NewLazyDLL(dllPath)
	if err := dll.Load(); err != nil {
		return nil, fmt.Errorf("load %s: %w", dllPath, err)
	}

	// Filtering by process is not possible here: the network layer has no
	// process id. Every outbound packet is looked at and anything that is
	// not a selected program's is put straight back.
	filter := fmt.Sprintf("outbound and !loopback and ip and (tcp or udp) and ip.DstAddr != %s", relayIP)
	filterPtr, err := windows.BytePtrFromString(filter)
	if err != nil {
		return nil, err
	}
	handle, _, callErr := dll.NewProc("WinDivertOpen").Call(
		uintptr(unsafe.Pointer(filterPtr)), wdLayerNetwork, 0, 0)
	if windows.Handle(handle) == windows.InvalidHandle {
		return nil, describeOpenError(callErr)
	}

	// Generous queues: under load the default (small) queue drops packets
	// of every program on the machine, not just the game's.
	setParam := dll.NewProc("WinDivertSetParam")
	setParam.Call(handle, wdParamQueueLength, 16384)
	setParam.Call(handle, wdParamQueueTime, 2000)
	setParam.Call(handle, wdParamQueueSize, 32<<20)

	return &winDivert{
		handle:   windows.Handle(handle),
		recv:     dll.NewProc("WinDivertRecv"),
		send:     dll.NewProc("WinDivertSend"),
		shutdown: dll.NewProc("WinDivertShutdown"),
		close:    dll.NewProc("WinDivertClose"),
	}, nil
}

func describeOpenError(err error) error {
	var errno windows.Errno
	if !errors.As(err, &errno) {
		return fmt.Errorf("WinDivertOpen: %w", err)
	}
	switch errno {
	case windows.ERROR_ACCESS_DENIED:
		return errors.New("WinDivertOpen: access denied — the engine must run as administrator")
	case windows.ERROR_FILE_NOT_FOUND:
		return errors.New("WinDivertOpen: WinDivert64.sys is missing next to WinDivert.dll")
	case 577: // ERROR_INVALID_IMAGE_HASH
		return errors.New("WinDivertOpen: Windows refused the driver's signature")
	case 1275: // ERROR_DRIVER_BLOCKED
		return errors.New("WinDivertOpen: the driver was blocked from loading (security software, or a non-local folder)")
	case 1058: // ERROR_SERVICE_DISABLED
		return errors.New("WinDivertOpen: a previous WinDivert driver is still marked for removal — reboot")
	}
	return fmt.Errorf("WinDivertOpen: %w", errno)
}

func (w *winDivert) Recv(buf []byte) (int, Meta, error) {
	var addr wdAddress
	var n uint32
	ok, _, err := w.recv.Call(uintptr(w.handle),
		uintptr(unsafe.Pointer(&buf[0])), uintptr(len(buf)),
		uintptr(unsafe.Pointer(&n)), uintptr(unsafe.Pointer(&addr)))
	if ok == 0 {
		return 0, Meta{}, fmt.Errorf("WinDivertRecv: %w", err)
	}
	return int(n), Meta{IfIdx: addr.IfIdx, SubIfIdx: addr.SubIfIdx, Flags: addr.Flags}, nil
}

func (w *winDivert) sendWith(pkt []byte, addr *wdAddress) error {
	var n uint32
	ok, _, err := w.send.Call(uintptr(w.handle),
		uintptr(unsafe.Pointer(&pkt[0])), uintptr(len(pkt)),
		uintptr(unsafe.Pointer(&n)), uintptr(unsafe.Pointer(addr)))
	if ok == 0 {
		return fmt.Errorf("WinDivertSend: %w", err)
	}
	return nil
}

// Reinject hands the packet back with exactly the flags it was captured
// with, so pending checksum/segmentation offload still happens as planned.
func (w *winDivert) Reinject(pkt []byte, meta Meta) error {
	if len(pkt) == 0 {
		return nil
	}
	return w.sendWith(pkt, &wdAddress{Flags: meta.Flags, IfIdx: meta.IfIdx, SubIfIdx: meta.SubIfIdx})
}

// InjectInbound delivers a tunnel reply on the interface the connection
// went out on. Outbound is clear, and the checksum bits say the checksums
// are already complete, which the engine guarantees.
func (w *winDivert) InjectInbound(pkt []byte, meta Meta) error {
	if len(pkt) == 0 {
		return nil
	}
	return w.sendWith(pkt, &wdAddress{
		Flags:    wdFlagIPChecksum | wdFlagTCPChecksum | wdFlagUDPChecksum,
		IfIdx:    meta.IfIdx,
		SubIfIdx: meta.SubIfIdx,
	})
}

func (w *winDivert) Close() error {
	w.closeOnce.Do(func() {
		// Shutdown first: it wakes the blocked Recv and lets queued packets
		// drain instead of being dropped with the handle.
		w.shutdown.Call(uintptr(w.handle), wdShutdownBoth)
		w.close.Call(uintptr(w.handle))
	})
	return nil
}
