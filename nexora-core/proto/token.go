package proto

import (
	"bytes"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"time"
)

// Token is what the backend signs to let one device open a relay session.
// The relay never talks to the backend: it only checks the HMAC with the
// secret both sides share, so relays stay stateless and easy to add.
type Token struct {
	// UserID and Device together identify a session: reconnecting with the
	// same pair keeps the same virtual IP, so NAT state on the relay (and
	// therefore the game's open connections) survives a short network blip.
	UserID  string `json:"uid"`
	Device  string `json:"dev"`
	Expires int64  `json:"exp"`
}

var (
	ErrTokenFormat    = errors.New("token: malformed")
	ErrTokenSignature = errors.New("token: bad signature")
	ErrTokenExpired   = errors.New("token: expired")
)

var b64 = base64.RawURLEncoding

// SignToken encodes token as base64url(json) "." base64url(hmac-sha256).
func SignToken(secret []byte, token Token) ([]byte, error) {
	body, err := json.Marshal(token)
	if err != nil {
		return nil, err
	}
	encoded := make([]byte, b64.EncodedLen(len(body)))
	b64.Encode(encoded, body)
	mac := hmac.New(sha256.New, secret)
	mac.Write(encoded)
	sig := mac.Sum(nil)
	out := append(encoded, '.')
	return b64.AppendEncode(out, sig), nil
}

// VerifyToken checks the signature and expiry of a signed token.
func VerifyToken(secret, signed []byte, now time.Time) (Token, error) {
	var token Token
	dot := bytes.IndexByte(signed, '.')
	if dot <= 0 || dot == len(signed)-1 {
		return token, ErrTokenFormat
	}
	encoded, sigPart := signed[:dot], signed[dot+1:]
	sig, err := b64.AppendDecode(nil, sigPart)
	if err != nil {
		return token, ErrTokenFormat
	}
	mac := hmac.New(sha256.New, secret)
	mac.Write(encoded)
	if !hmac.Equal(sig, mac.Sum(nil)) {
		return token, ErrTokenSignature
	}
	body, err := b64.AppendDecode(nil, encoded)
	if err != nil {
		return token, ErrTokenFormat
	}
	if err := json.Unmarshal(body, &token); err != nil {
		return token, ErrTokenFormat
	}
	if token.UserID == "" {
		return token, ErrTokenFormat
	}
	if now.Unix() >= token.Expires {
		return token, ErrTokenExpired
	}
	return token, nil
}
