//go:build linux

package relay

import (
	"fmt"
	"net/netip"
	"os"
	"os/exec"
	"strings"
)

// Firewall is the kernel configuration that turns the TUN device into an
// internet gateway for tunnel clients. The kernel's own connection tracking
// does all the NAT, so there is no NAT table to maintain in this program.
type Firewall struct {
	rules [][]string
}

func firewallRules(tunName string, pool netip.Prefix) [][]string {
	return [][]string{
		// Rewrite client traffic leaving for the internet to the relay's
		// own address; replies are translated back automatically.
		{"-t", "nat", "POSTROUTING", "-s", pool.String(), "!", "-o", tunName, "-j", "MASQUERADE"},
		{"FORWARD", "-i", tunName, "-j", "ACCEPT"},
		{"FORWARD", "-o", tunName, "-m", "conntrack", "--ctstate", "RELATED,ESTABLISHED", "-j", "ACCEPT"},
		// Tunnel clients are customers, not administrators: they get the
		// internet through this host, never the host's own services.
		{"INPUT", "-i", tunName, "-j", "DROP"},
	}
}

// rule is [-t table] CHAIN match...; op is -C, -I or -D.
func iptables(op string, rule []string) error {
	var args []string
	rest := rule
	if rule[0] == "-t" {
		args = append(args, rule[0], rule[1])
		rest = rule[2:]
	}
	args = append(args, op)
	args = append(args, rest...)
	out, err := exec.Command("iptables", args...).CombinedOutput()
	if err != nil {
		return fmt.Errorf("iptables %s: %w: %s", strings.Join(args, " "), err, strings.TrimSpace(string(out)))
	}
	return nil
}

// SetupFirewall enables forwarding and installs the rules idempotently.
func SetupFirewall(tunName string, pool netip.Prefix) (*Firewall, error) {
	if err := os.WriteFile("/proc/sys/net/ipv4/ip_forward", []byte("1\n"), 0o644); err != nil {
		return nil, fmt.Errorf("enable ip_forward: %w", err)
	}
	fw := &Firewall{}
	for _, rule := range firewallRules(tunName, pool) {
		if iptables("-C", rule) == nil {
			continue
		}
		if err := iptables("-I", rule); err != nil {
			fw.Remove()
			return nil, err
		}
		fw.rules = append(fw.rules, rule)
	}
	return fw, nil
}

// Remove deletes only the rules this process added.
func (fw *Firewall) Remove() {
	for _, rule := range fw.rules {
		iptables("-D", rule)
	}
	fw.rules = nil
}
