//go:build windows

// nexora-engine is the Windows client side of the Nexora tunnel. It must run
// as administrator, with WinDivert.dll and WinDivert64.sys beside it.
//
//	nexora-engine connect -relay HOST:PORT -pubkey KEY -token TOKEN -exe game.exe [-dir "C:\Games\X"]
//	    route the named programs through the relay and print status (for testing)
//	nexora-engine serve -key-file PATH [-listen 127.0.0.1:47600]
//	    run the local control API for the desktop app
//	nexora-engine probe HOST:PORT [HOST:PORT ...]
//	    measure round-trip time to relays
package main

import (
	"crypto/rand"
	"encoding/hex"
	"errors"
	"flag"
	"fmt"
	"net"
	"net/http"
	"net/netip"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"time"

	"golang.org/x/sys/windows"

	"nexora.app/core/engine"
)

type multiFlag []string

func (m *multiFlag) String() string     { return strings.Join(*m, ",") }
func (m *multiFlag) Set(v string) error { *m = append(*m, v); return nil }

func main() {
	if len(os.Args) < 2 {
		usage()
	}
	var err error
	switch os.Args[1] {
	case "connect":
		err = cmdConnect(os.Args[2:])
	case "serve":
		err = cmdServe(os.Args[2:])
	case "probe":
		err = cmdProbe(os.Args[2:])
	default:
		usage()
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, "nexora-engine:", err)
		os.Exit(1)
	}
}

func usage() {
	fmt.Fprintln(os.Stderr, "usage: nexora-engine connect|serve|probe [flags]")
	os.Exit(2)
}

func requireAdmin() error {
	if !windows.GetCurrentProcessToken().IsElevated() {
		return errors.New("must be run as administrator (right-click the terminal → Run as administrator)")
	}
	return nil
}

// build is the engine.Factory for Windows: real WinDivert capture and the
// real socket-owner lookup.
func build(cfg engine.StartConfig) (*engine.Engine, error) {
	tunnel, err := engine.NewTunnel(cfg.Relay, cfg.RelayPublicKey, cfg.Token)
	if err != nil {
		return nil, err
	}
	capture, err := engine.OpenCapture(netip.AddrFrom4(tunnel.RelayIP()))
	if err != nil {
		tunnel.Close()
		return nil, err
	}
	return engine.New(capture, engine.NewResolver(), tunnel, cfg.Rules), nil
}

func cmdConnect(args []string) error {
	fs := flag.NewFlagSet("connect", flag.ExitOnError)
	relay := fs.String("relay", "", "relay address, HOST:PORT")
	pubkey := fs.String("pubkey", "", "relay public key (base64)")
	token := fs.String("token", "", "session token")
	var exes, dirs multiFlag
	fs.Var(&exes, "exe", "program file name to route, e.g. game.exe (repeatable)")
	fs.Var(&dirs, "dir", "install folder whose programs are all routed (repeatable)")
	fs.Parse(args)
	if len(exes) == 0 && len(dirs) == 0 {
		return errors.New("give at least one -exe or -dir")
	}
	if err := requireAdmin(); err != nil {
		return err
	}

	eng, err := build(engine.StartConfig{
		Relay: *relay, RelayPublicKey: *pubkey, Token: *token,
		Rules: []engine.Rule{{Name: "cli", Exes: exes, Dirs: dirs}},
	})
	if err != nil {
		return err
	}
	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt)
	finished := make(chan error, 1)
	go func() { finished <- eng.Run() }()

	fmt.Println("engine running — start the game now. Ctrl+C to stop.")
	ticker := time.NewTicker(2 * time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-stop:
			eng.Close()
			return nil
		case err := <-finished:
			return err
		case <-ticker.C:
			printStatus(eng.Status())
		}
	}
}

func printStatus(status engine.Status) {
	t := status.Tunnel
	if !t.Connected {
		fmt.Printf("tunnel: NOT CONNECTED to %s  %s\n", t.Relay, t.Error)
		return
	}
	fmt.Printf("tunnel: up via %s  ping %.1f ms  loss %.1f%%  sent %d B  received %d B  routed connections: %d\n",
		t.Relay, t.RTTMs, t.LossPct, t.BytesOut, t.BytesIn, len(status.Flows))
	for _, f := range status.Flows {
		fmt.Printf("   %-22s %s :%-5d -> %-21s out %-9d in %d\n", f.Exe, f.Protocol, f.LocalPort, f.Remote, f.BytesOut, f.BytesIn)
	}
}

func cmdServe(args []string) error {
	fs := flag.NewFlagSet("serve", flag.ExitOnError)
	listen := fs.String("listen", "127.0.0.1:47600", "address for the control API (loopback only)")
	keyFile := fs.String("key-file", "", "file to write the API key to (created if missing)")
	fs.Parse(args)
	if *keyFile == "" {
		return errors.New("-key-file is required")
	}
	if err := requireAdmin(); err != nil {
		return err
	}
	host, _, err := net.SplitHostPort(*listen)
	if err != nil {
		return err
	}
	if ip := net.ParseIP(host); ip == nil || !ip.IsLoopback() {
		return errors.New("-listen must be a loopback address: this API controls an elevated process")
	}

	key, err := loadOrCreateKey(*keyFile)
	if err != nil {
		return err
	}
	controller := engine.NewController(build, key)
	defer controller.Stop()

	server := &http.Server{Addr: *listen, Handler: controller.Handler(), ReadHeaderTimeout: 5 * time.Second}
	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt)
	go func() {
		<-stop
		controller.Stop()
		server.Close()
	}()
	fmt.Printf("control API on http://%s (key in %s)\n", *listen, *keyFile)
	if err := server.ListenAndServe(); !errors.Is(err, http.ErrServerClosed) {
		return err
	}
	return nil
}

func loadOrCreateKey(path string) (string, error) {
	if raw, err := os.ReadFile(path); err == nil {
		if key := strings.TrimSpace(string(raw)); len(key) >= 32 {
			return key, nil
		}
	}
	raw := make([]byte, 32)
	if _, err := rand.Read(raw); err != nil {
		return "", err
	}
	key := hex.EncodeToString(raw)
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return "", err
	}
	return key, os.WriteFile(path, []byte(key+"\n"), 0o600)
}

func cmdProbe(args []string) error {
	if len(args) == 0 {
		return errors.New("give at least one HOST:PORT")
	}
	for _, r := range engine.Probe(args, 5, time.Second) {
		if r.OK {
			fmt.Printf("%-28s %7.1f ms  (lost %d/5)\n", r.Relay, r.RTTMs, r.Lost)
		} else {
			fmt.Printf("%-28s unreachable\n", r.Relay)
		}
	}
	return nil
}
