package relay

import (
	"crypto/ecdh"
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"net/netip"
	"os"

	"nexora.app/core/proto"
)

// Config is the relay's JSON config file.
type Config struct {
	Listen         string `json:"listen"`
	PrivateKey     string `json:"private_key"`
	TokenSecret    string `json:"token_secret"`
	Pool           string `json:"pool"`
	TunName        string `json:"tun_name"`
	ManageFirewall bool   `json:"manage_firewall"`
	IdleSeconds    int    `json:"idle_seconds"`
	MaxSessions    int    `json:"max_sessions"`
}

// NewConfig returns a config with fresh keys and sensible defaults.
func NewConfig() (Config, error) {
	key, err := proto.GenerateKey()
	if err != nil {
		return Config{}, err
	}
	secret := make([]byte, 32)
	if _, err := rand.Read(secret); err != nil {
		return Config{}, err
	}
	return Config{
		Listen:         ":4700",
		PrivateKey:     base64.StdEncoding.EncodeToString(key.Bytes()),
		TokenSecret:    base64.StdEncoding.EncodeToString(secret),
		Pool:           "10.66.0.0/16",
		TunName:        "nexora0",
		ManageFirewall: true,
		IdleSeconds:    180,
	}, nil
}

func LoadConfig(path string) (Config, error) {
	var cfg Config
	raw, err := os.ReadFile(path)
	if err != nil {
		return cfg, err
	}
	if err := json.Unmarshal(raw, &cfg); err != nil {
		return cfg, fmt.Errorf("%s: %w", path, err)
	}
	return cfg, nil
}

// Keys decodes the config's secrets.
func (c Config) Keys() (*ecdh.PrivateKey, []byte, error) {
	raw, err := base64.StdEncoding.DecodeString(c.PrivateKey)
	if err != nil {
		return nil, nil, fmt.Errorf("private_key: %w", err)
	}
	key, err := proto.ParsePrivateKey(raw)
	if err != nil {
		return nil, nil, fmt.Errorf("private_key: %w", err)
	}
	secret, err := base64.StdEncoding.DecodeString(c.TokenSecret)
	if err != nil {
		return nil, nil, fmt.Errorf("token_secret: %w", err)
	}
	if len(secret) < 16 {
		return nil, nil, errors.New("token_secret: must be at least 16 bytes")
	}
	return key, secret, nil
}

func (c Config) PoolPrefix() (netip.Prefix, error) {
	prefix, err := netip.ParsePrefix(c.Pool)
	if err != nil {
		return netip.Prefix{}, fmt.Errorf("pool: %w", err)
	}
	return prefix.Masked(), nil
}

// PublicKey is what clients need to know about this relay.
func (c Config) PublicKey() (string, error) {
	key, _, err := c.Keys()
	if err != nil {
		return "", err
	}
	return base64.StdEncoding.EncodeToString(key.PublicKey().Bytes()), nil
}
