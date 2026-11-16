// Package proto is the Nexora tunnel wire protocol shared by the Windows
// engine and the Linux relay: a one-round-trip handshake followed by
// AEAD-sealed UDP datagrams that each carry one raw IPv4 packet.
//
// Handshake (NK-shaped: the client knows the relay's static key in advance,
// the client itself is authenticated by a backend-signed token):
//
//	es = X25519(clientEph, relayStatic)       hello key  = HKDF(es)
//	ee = X25519(clientEph, relayEph)          session keys = HKDF(es || ee)
//
// Transport datagram: type(1) | session id(8) | counter(8) | AEAD(payload).
package proto

import (
	"crypto/cipher"
	"crypto/ecdh"
	"crypto/hkdf"
	"crypto/rand"
	"crypto/sha256"
	"encoding/binary"
	"errors"
	"sync"
	"sync/atomic"

	"golang.org/x/crypto/chacha20poly1305"
)

const (
	TypeHello      byte = 1
	TypeWelcome    byte = 2
	TypeData       byte = 3
	TypePing       byte = 4
	TypePong       byte = 5
	TypeBye        byte = 6
	TypeProbe      byte = 7
	TypeProbeReply byte = 8
	TypeReject     byte = 9

	Version byte = 1

	KeyLen    = 32
	HeaderLen = 1 + 8 + 8
	TagLen    = chacha20poly1305.Overhead
	// Overhead is what one transport datagram adds on top of the inner packet.
	Overhead = HeaderLen + TagLen

	// InnerMTU is the largest inner IPv4 packet either side will send. Outer
	// packet = 20 (IP) + 8 (UDP) + Overhead + InnerMTU = 1461, which still
	// fits a 1492-byte PPPoE path without outer fragmentation.
	InnerMTU = 1400

	ProbeLen = 1 + 8

	RejectBadToken  byte = 1
	RejectExpired   byte = 2
	RejectFull      byte = 3
	RejectBadHello  byte = 4
	welcomeBodyLen       = 8 + 4 + 2 + 2
	helloFixedLen        = 1 + 1 + KeyLen
	welcomeFixedLen      = 1 + KeyLen
)

var (
	ErrShort     = errors.New("proto: datagram too short")
	ErrVersion   = errors.New("proto: unsupported protocol version")
	ErrAuth      = errors.New("proto: authentication failed")
	ErrReplay    = errors.New("proto: replayed or too-old counter")
	ErrWrongType = errors.New("proto: unexpected message type")
)

// GenerateKey returns a new X25519 private key.
func GenerateKey() (*ecdh.PrivateKey, error) {
	return ecdh.X25519().GenerateKey(rand.Reader)
}

func ParsePublicKey(b []byte) (*ecdh.PublicKey, error) {
	return ecdh.X25519().NewPublicKey(b)
}

func ParsePrivateKey(b []byte) (*ecdh.PrivateKey, error) {
	return ecdh.X25519().NewPrivateKey(b)
}

func deriveHelloKey(es []byte, clientEph, relayStatic *ecdh.PublicKey) ([]byte, error) {
	info := append([]byte("nexora hello v1"), clientEph.Bytes()...)
	info = append(info, relayStatic.Bytes()...)
	return hkdf.Key(sha256.New, es, nil, string(info), KeyLen)
}

func deriveSessionKeys(es, ee []byte, clientEph, relayEph, relayStatic *ecdh.PublicKey) (c2s, s2c []byte, err error) {
	secret := append(append([]byte{}, es...), ee...)
	info := append([]byte("nexora session v1"), clientEph.Bytes()...)
	info = append(info, relayEph.Bytes()...)
	info = append(info, relayStatic.Bytes()...)
	okm, err := hkdf.Key(sha256.New, secret, nil, string(info), 2*KeyLen)
	if err != nil {
		return nil, nil, err
	}
	return okm[:KeyLen], okm[KeyLen:], nil
}

func nonceFor(counter uint64) []byte {
	nonce := make([]byte, chacha20poly1305.NonceSize)
	binary.BigEndian.PutUint64(nonce[4:], counter)
	return nonce
}

// ClientHandshake holds the client's half of an in-flight handshake.
type ClientHandshake struct {
	eph         *ecdh.PrivateKey
	relayStatic *ecdh.PublicKey
	es          []byte
	helloKey    cipher.AEAD
}

// NewClientHello builds the HELLO datagram carrying the backend-issued token.
func NewClientHello(relayStatic *ecdh.PublicKey, token []byte) (*ClientHandshake, []byte, error) {
	eph, err := GenerateKey()
	if err != nil {
		return nil, nil, err
	}
	es, err := eph.ECDH(relayStatic)
	if err != nil {
		return nil, nil, err
	}
	key, err := deriveHelloKey(es, eph.PublicKey(), relayStatic)
	if err != nil {
		return nil, nil, err
	}
	aead, err := chacha20poly1305.New(key)
	if err != nil {
		return nil, nil, err
	}
	msg := make([]byte, 0, helloFixedLen+len(token)+TagLen)
	msg = append(msg, TypeHello, Version)
	msg = append(msg, eph.PublicKey().Bytes()...)
	msg = aead.Seal(msg, nonceFor(0), token, msg[:helloFixedLen])
	return &ClientHandshake{eph: eph, relayStatic: relayStatic, es: es, helloKey: aead}, msg, nil
}

// Welcome is what the relay assigns to a new session.
type Welcome struct {
	SessionID   uint64
	VirtualIP   [4]byte
	MTU         uint16
	IdleSeconds uint16
}

// Finish consumes the relay's WELCOME (or REJECT) and yields the session.
func (h *ClientHandshake) Finish(datagram []byte) (*Session, Welcome, error) {
	var w Welcome
	if len(datagram) < 1 {
		return nil, w, ErrShort
	}
	if datagram[0] == TypeReject {
		code, err := h.helloKey.Open(nil, nonceFor(1), datagram[1:], datagram[:1])
		if err != nil || len(code) != 1 {
			return nil, w, ErrAuth
		}
		return nil, w, &RejectError{Code: code[0]}
	}
	if datagram[0] != TypeWelcome {
		return nil, w, ErrWrongType
	}
	if len(datagram) < welcomeFixedLen+welcomeBodyLen+TagLen {
		return nil, w, ErrShort
	}
	relayEph, err := ParsePublicKey(datagram[1:welcomeFixedLen])
	if err != nil {
		return nil, w, ErrAuth
	}
	ee, err := h.eph.ECDH(relayEph)
	if err != nil {
		return nil, w, ErrAuth
	}
	c2s, s2c, err := deriveSessionKeys(h.es, ee, h.eph.PublicKey(), relayEph, h.relayStatic)
	if err != nil {
		return nil, w, err
	}
	recv, _ := chacha20poly1305.New(s2c)
	body, err := recv.Open(nil, nonceFor(0), datagram[welcomeFixedLen:], datagram[:welcomeFixedLen])
	if err != nil || len(body) != welcomeBodyLen {
		return nil, w, ErrAuth
	}
	w.SessionID = binary.BigEndian.Uint64(body[0:8])
	copy(w.VirtualIP[:], body[8:12])
	w.MTU = binary.BigEndian.Uint16(body[12:14])
	w.IdleSeconds = binary.BigEndian.Uint16(body[14:16])
	send, _ := chacha20poly1305.New(c2s)
	return newSession(w.SessionID, send, recv), w, nil
}

// RejectError is an authenticated refusal from the relay.
type RejectError struct{ Code byte }

func (e *RejectError) Error() string {
	switch e.Code {
	case RejectBadToken:
		return "relay rejected the session token"
	case RejectExpired:
		return "session token has expired"
	case RejectFull:
		return "relay has no free addresses"
	default:
		return "relay rejected the handshake"
	}
}

// ServerHello is a HELLO the relay has decrypted but not yet answered.
type ServerHello struct {
	Token     []byte
	ClientEph *ecdh.PublicKey
	es        []byte
	helloKey  cipher.AEAD
}

// OpenHello authenticates a HELLO against the relay's static key and returns
// the token for the caller to verify before calling Accept or Reject.
func OpenHello(relayStatic *ecdh.PrivateKey, datagram []byte) (*ServerHello, error) {
	if len(datagram) < helloFixedLen+TagLen {
		return nil, ErrShort
	}
	if datagram[0] != TypeHello {
		return nil, ErrWrongType
	}
	if datagram[1] != Version {
		return nil, ErrVersion
	}
	clientEph, err := ParsePublicKey(datagram[2:helloFixedLen])
	if err != nil {
		return nil, ErrAuth
	}
	es, err := relayStatic.ECDH(clientEph)
	if err != nil {
		return nil, ErrAuth
	}
	key, err := deriveHelloKey(es, clientEph, relayStatic.PublicKey())
	if err != nil {
		return nil, err
	}
	aead, _ := chacha20poly1305.New(key)
	token, err := aead.Open(nil, nonceFor(0), datagram[helloFixedLen:], datagram[:helloFixedLen])
	if err != nil {
		return nil, ErrAuth
	}
	return &ServerHello{Token: token, ClientEph: clientEph, es: es, helloKey: aead}, nil
}

// Accept completes the handshake on the relay side.
func (h *ServerHello) Accept(relayStatic *ecdh.PrivateKey, w Welcome) (*Session, []byte, error) {
	relayEph, err := GenerateKey()
	if err != nil {
		return nil, nil, err
	}
	ee, err := relayEph.ECDH(h.ClientEph)
	if err != nil {
		return nil, nil, ErrAuth
	}
	c2s, s2c, err := deriveSessionKeys(h.es, ee, h.ClientEph, relayEph.PublicKey(), relayStatic.PublicKey())
	if err != nil {
		return nil, nil, err
	}
	send, _ := chacha20poly1305.New(s2c)
	recv, _ := chacha20poly1305.New(c2s)

	body := make([]byte, welcomeBodyLen)
	binary.BigEndian.PutUint64(body[0:8], w.SessionID)
	copy(body[8:12], w.VirtualIP[:])
	binary.BigEndian.PutUint16(body[12:14], w.MTU)
	binary.BigEndian.PutUint16(body[14:16], w.IdleSeconds)

	msg := make([]byte, 0, welcomeFixedLen+welcomeBodyLen+TagLen)
	msg = append(msg, TypeWelcome)
	msg = append(msg, relayEph.PublicKey().Bytes()...)
	msg = send.Seal(msg, nonceFor(0), body, msg[:welcomeFixedLen])
	return newSession(w.SessionID, send, recv), msg, nil
}

// Reject builds an authenticated refusal only the HELLO's sender can verify.
func (h *ServerHello) Reject(code byte) []byte {
	msg := []byte{TypeReject}
	return h.helloKey.Seal(msg, nonceFor(1), []byte{code}, msg[:1])
}

// Session seals and opens transport datagrams for one direction pair.
type Session struct {
	ID      uint64
	send    cipher.AEAD
	recv    cipher.AEAD
	sendCtr atomic.Uint64

	replayMu sync.Mutex
	replay   ReplayWindow
}

func newSession(id uint64, send, recv cipher.AEAD) *Session {
	return &Session{ID: id, send: send, recv: recv}
}

// Seal appends one transport datagram to dst.
func (s *Session) Seal(dst []byte, typ byte, payload []byte) []byte {
	counter := s.sendCtr.Add(1)
	start := len(dst)
	dst = append(dst, typ)
	dst = binary.BigEndian.AppendUint64(dst, s.ID)
	dst = binary.BigEndian.AppendUint64(dst, counter)
	return s.send.Seal(dst, nonceFor(counter), payload, dst[start:start+HeaderLen])
}

// Open authenticates a transport datagram and appends its payload to dst.
func (s *Session) Open(dst, datagram []byte) (typ byte, payload []byte, err error) {
	if len(datagram) < Overhead {
		return 0, nil, ErrShort
	}
	counter := binary.BigEndian.Uint64(datagram[9:17])
	s.replayMu.Lock()
	fresh := s.replay.Check(counter)
	s.replayMu.Unlock()
	if !fresh {
		return 0, nil, ErrReplay
	}
	payload, err = s.recv.Open(dst, nonceFor(counter), datagram[HeaderLen:], datagram[:HeaderLen])
	if err != nil {
		return 0, nil, ErrAuth
	}
	s.replayMu.Lock()
	fresh = s.replay.Mark(counter)
	s.replayMu.Unlock()
	if !fresh {
		return 0, nil, ErrReplay
	}
	return datagram[0], payload, nil
}

// PeekSessionID reads the session id of a transport datagram without
// authenticating it, so the relay can find the session to authenticate with.
func PeekSessionID(datagram []byte) (uint64, bool) {
	if len(datagram) < Overhead {
		return 0, false
	}
	switch datagram[0] {
	case TypeData, TypePing, TypePong, TypeBye:
		return binary.BigEndian.Uint64(datagram[1:9]), true
	}
	return 0, false
}
