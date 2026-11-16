//go:build linux

package relay

import (
	"fmt"
	"net/netip"
	"os"

	"golang.org/x/sys/unix"
)

// OpenTUN creates (or attaches to) a layer-3 TUN device, gives it the
// gateway address of prefix and brings it up, using ioctls directly so the
// relay needs no `ip` binary on the host.
func OpenTUN(name string, prefix netip.Prefix, mtu int) (*os.File, error) {
	fd, err := unix.Open("/dev/net/tun", unix.O_RDWR|unix.O_CLOEXEC|unix.O_NONBLOCK, 0)
	if err != nil {
		return nil, fmt.Errorf("open /dev/net/tun: %w", err)
	}
	ifr, err := unix.NewIfreq(name)
	if err != nil {
		unix.Close(fd)
		return nil, err
	}
	ifr.SetUint16(unix.IFF_TUN | unix.IFF_NO_PI)
	if err := unix.IoctlIfreq(fd, unix.TUNSETIFF, ifr); err != nil {
		unix.Close(fd)
		return nil, fmt.Errorf("TUNSETIFF %s: %w", name, err)
	}
	if err := configureInterface(name, prefix, mtu); err != nil {
		unix.Close(fd)
		return nil, err
	}
	return os.NewFile(uintptr(fd), "/dev/net/tun"), nil
}

func configureInterface(name string, prefix netip.Prefix, mtu int) error {
	sock, err := unix.Socket(unix.AF_INET, unix.SOCK_DGRAM|unix.SOCK_CLOEXEC, 0)
	if err != nil {
		return err
	}
	defer unix.Close(sock)

	set := func(request uint, fill func(*unix.Ifreq) error, what string) error {
		ifr, err := unix.NewIfreq(name)
		if err != nil {
			return err
		}
		if err := fill(ifr); err != nil {
			return err
		}
		if err := unix.IoctlIfreq(sock, request, ifr); err != nil {
			return fmt.Errorf("set %s on %s: %w", what, name, err)
		}
		return nil
	}

	gateway := GatewayAddr(prefix).As4()
	mask := maskOf(prefix.Bits())
	if err := set(unix.SIOCSIFADDR, func(i *unix.Ifreq) error { return i.SetInet4Addr(gateway[:]) }, "address"); err != nil {
		return err
	}
	if err := set(unix.SIOCSIFNETMASK, func(i *unix.Ifreq) error { return i.SetInet4Addr(mask[:]) }, "netmask"); err != nil {
		return err
	}
	if err := set(unix.SIOCSIFMTU, func(i *unix.Ifreq) error { i.SetUint32(uint32(mtu)); return nil }, "mtu"); err != nil {
		return err
	}

	flags, err := unix.NewIfreq(name)
	if err != nil {
		return err
	}
	if err := unix.IoctlIfreq(sock, unix.SIOCGIFFLAGS, flags); err != nil {
		return fmt.Errorf("get flags on %s: %w", name, err)
	}
	flags.SetUint16(flags.Uint16() | unix.IFF_UP | unix.IFF_RUNNING)
	if err := unix.IoctlIfreq(sock, unix.SIOCSIFFLAGS, flags); err != nil {
		return fmt.Errorf("bring up %s: %w", name, err)
	}
	return nil
}

func maskOf(bits int) [4]byte {
	var mask [4]byte
	value := ^uint32(0) << (32 - bits)
	mask[0], mask[1], mask[2], mask[3] = byte(value>>24), byte(value>>16), byte(value>>8), byte(value)
	return mask
}
