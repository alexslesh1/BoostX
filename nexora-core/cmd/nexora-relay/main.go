//go:build linux

// nexora-relay is the server side of the Nexora tunnel.
//
//	nexora-relay init  -out /etc/nexora/relay.json   create a config with fresh keys
//	nexora-relay run   -config /etc/nexora/relay.json
//	nexora-relay pubkey -config ...                   print the key clients need
//	nexora-relay token -config ... -uid U -dev D      mint a test session token
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"log/slog"
	"net"
	"os"
	"os/signal"
	"syscall"
	"time"

	"nexora.app/core/proto"
	"nexora.app/core/relay"
)

func main() {
	if len(os.Args) < 2 {
		usage()
	}
	var err error
	switch os.Args[1] {
	case "init":
		err = cmdInit(os.Args[2:])
	case "run":
		err = cmdRun(os.Args[2:])
	case "pubkey":
		err = cmdPubkey(os.Args[2:])
	case "token":
		err = cmdToken(os.Args[2:])
	default:
		usage()
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, "nexora-relay:", err)
		os.Exit(1)
	}
}

func usage() {
	fmt.Fprintln(os.Stderr, "usage: nexora-relay init|run|pubkey|token [flags]")
	os.Exit(2)
}

func cmdInit(args []string) error {
	fs := flag.NewFlagSet("init", flag.ExitOnError)
	out := fs.String("out", "relay.json", "config file to create")
	fs.Parse(args)

	cfg, err := relay.NewConfig()
	if err != nil {
		return err
	}
	raw, _ := json.MarshalIndent(cfg, "", "  ")
	// O_EXCL: never overwrite an existing config and silently rotate keys
	// that clients and the backend already depend on.
	file, err := os.OpenFile(*out, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o600)
	if err != nil {
		return err
	}
	defer file.Close()
	if _, err := file.Write(append(raw, '\n')); err != nil {
		return err
	}
	pub, _ := cfg.PublicKey()
	fmt.Printf("wrote %s\nrelay public key (give this to clients): %s\n", *out, pub)
	return nil
}

func cmdPubkey(args []string) error {
	fs := flag.NewFlagSet("pubkey", flag.ExitOnError)
	path := fs.String("config", "relay.json", "config file")
	fs.Parse(args)
	cfg, err := relay.LoadConfig(*path)
	if err != nil {
		return err
	}
	pub, err := cfg.PublicKey()
	if err != nil {
		return err
	}
	fmt.Println(pub)
	return nil
}

func cmdToken(args []string) error {
	fs := flag.NewFlagSet("token", flag.ExitOnError)
	path := fs.String("config", "relay.json", "config file")
	uid := fs.String("uid", "test-user", "user id")
	dev := fs.String("dev", "test-device", "device id")
	ttl := fs.Duration("ttl", 24*time.Hour, "token lifetime")
	fs.Parse(args)
	cfg, err := relay.LoadConfig(*path)
	if err != nil {
		return err
	}
	_, secret, err := cfg.Keys()
	if err != nil {
		return err
	}
	signed, err := proto.SignToken(secret, proto.Token{UserID: *uid, Device: *dev, Expires: time.Now().Add(*ttl).Unix()})
	if err != nil {
		return err
	}
	fmt.Println(string(signed))
	return nil
}

func cmdRun(args []string) error {
	fs := flag.NewFlagSet("run", flag.ExitOnError)
	path := fs.String("config", "relay.json", "config file")
	fs.Parse(args)

	cfg, err := relay.LoadConfig(*path)
	if err != nil {
		return err
	}
	key, secret, err := cfg.Keys()
	if err != nil {
		return err
	}
	pool, err := cfg.PoolPrefix()
	if err != nil {
		return err
	}
	log := slog.New(slog.NewTextHandler(os.Stderr, nil))

	tun, err := relay.OpenTUN(cfg.TunName, pool, proto.InnerMTU)
	if err != nil {
		return err
	}
	if cfg.ManageFirewall {
		firewall, err := relay.SetupFirewall(cfg.TunName, pool)
		if err != nil {
			tun.Close()
			return err
		}
		defer firewall.Remove()
	}

	addr, err := net.ResolveUDPAddr("udp4", cfg.Listen)
	if err != nil {
		return err
	}
	conn, err := net.ListenUDP("udp4", addr)
	if err != nil {
		return err
	}
	server, err := relay.New(conn, tun, relay.Options{
		StaticKey:   key,
		TokenSecret: secret,
		Pool:        pool,
		IdleTimeout: time.Duration(cfg.IdleSeconds) * time.Second,
		MaxSessions: cfg.MaxSessions,
		Logger:      log,
	})
	if err != nil {
		return err
	}

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)
	go func() {
		<-stop
		log.Info("shutting down")
		server.Close()
	}()

	log.Info("relay listening", "addr", conn.LocalAddr().String(), "tun", cfg.TunName, "pool", pool.String())
	return server.Serve()
}
