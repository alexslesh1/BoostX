package proto

import (
	"bytes"
	"errors"
	"testing"
	"time"
)

func handshake(t *testing.T) (client, server *Session, w Welcome) {
	t.Helper()
	relayStatic, err := GenerateKey()
	if err != nil {
		t.Fatal(err)
	}
	hs, hello, err := NewClientHello(relayStatic.PublicKey(), []byte("token-bytes"))
	if err != nil {
		t.Fatal(err)
	}
	opened, err := OpenHello(relayStatic, hello)
	if err != nil {
		t.Fatalf("OpenHello: %v", err)
	}
	if string(opened.Token) != "token-bytes" {
		t.Fatalf("token = %q", opened.Token)
	}
	want := Welcome{SessionID: 0xA1B2C3D4E5F60718, VirtualIP: [4]byte{10, 66, 0, 2}, MTU: InnerMTU, IdleSeconds: 180}
	server, welcome, err := opened.Accept(relayStatic, want)
	if err != nil {
		t.Fatal(err)
	}
	client, got, err := hs.Finish(welcome)
	if err != nil {
		t.Fatalf("Finish: %v", err)
	}
	if got != want {
		t.Fatalf("welcome = %+v, want %+v", got, want)
	}
	return client, server, got
}

func TestHandshakeAndTransportBothDirections(t *testing.T) {
	client, server, _ := handshake(t)

	up := client.Seal(nil, TypeData, []byte("client to relay"))
	if id, ok := PeekSessionID(up); !ok || id != client.ID {
		t.Fatalf("PeekSessionID = %x, %v", id, ok)
	}
	typ, payload, err := server.Open(nil, up)
	if err != nil || typ != TypeData || string(payload) != "client to relay" {
		t.Fatalf("server.Open = %d %q %v", typ, payload, err)
	}

	down := server.Seal(nil, TypePong, []byte("relay to client"))
	typ, payload, err = client.Open(nil, down)
	if err != nil || typ != TypePong || string(payload) != "relay to client" {
		t.Fatalf("client.Open = %d %q %v", typ, payload, err)
	}
	if len(up) != len("client to relay")+Overhead {
		t.Fatalf("overhead = %d, want %d", len(up)-len("client to relay"), Overhead)
	}
}

func TestTransportRejectsReplayTamperAndWrongDirection(t *testing.T) {
	client, server, _ := handshake(t)
	datagram := client.Seal(nil, TypeData, []byte("once"))

	if _, _, err := server.Open(nil, datagram); err != nil {
		t.Fatal(err)
	}
	if _, _, err := server.Open(nil, datagram); !errors.Is(err, ErrReplay) {
		t.Fatalf("replay err = %v, want ErrReplay", err)
	}

	tampered := client.Seal(nil, TypeData, []byte("payload"))
	tampered[len(tampered)-1] ^= 1
	if _, _, err := server.Open(nil, tampered); !errors.Is(err, ErrAuth) {
		t.Fatalf("tamper err = %v, want ErrAuth", err)
	}

	// The header is authenticated too: flipping DATA to BYE must not pass.
	retyped := client.Seal(nil, TypeData, []byte("payload"))
	retyped[0] = TypeBye
	if _, _, err := server.Open(nil, retyped); !errors.Is(err, ErrAuth) {
		t.Fatalf("retype err = %v, want ErrAuth", err)
	}

	// A client datagram reflected back at the client uses the wrong key.
	reflected := client.Seal(nil, TypeData, []byte("payload"))
	if _, _, err := client.Open(nil, reflected); !errors.Is(err, ErrAuth) {
		t.Fatalf("reflect err = %v, want ErrAuth", err)
	}
}

func TestOutOfOrderDeliveryWithinWindowIsAccepted(t *testing.T) {
	client, server, _ := handshake(t)
	var datagrams [][]byte
	for i := 0; i < 50; i++ {
		datagrams = append(datagrams, client.Seal(nil, TypeData, []byte{byte(i)}))
	}
	for _, i := range []int{49, 0, 10, 48, 1, 25} {
		if _, payload, err := server.Open(nil, datagrams[i]); err != nil || payload[0] != byte(i) {
			t.Fatalf("datagram %d: %v", i, err)
		}
	}
}

func TestHelloRejectsWrongRelayKeyAndTamper(t *testing.T) {
	relayStatic, _ := GenerateKey()
	otherRelay, _ := GenerateKey()
	_, hello, _ := NewClientHello(relayStatic.PublicKey(), []byte("tok"))

	if _, err := OpenHello(otherRelay, hello); !errors.Is(err, ErrAuth) {
		t.Fatalf("wrong relay key err = %v, want ErrAuth", err)
	}
	bad := bytes.Clone(hello)
	bad[len(bad)-1] ^= 1
	if _, err := OpenHello(relayStatic, bad); !errors.Is(err, ErrAuth) {
		t.Fatalf("tamper err = %v, want ErrAuth", err)
	}
	bad = bytes.Clone(hello)
	bad[1] = Version + 1
	if _, err := OpenHello(relayStatic, bad); !errors.Is(err, ErrVersion) {
		t.Fatalf("version err = %v, want ErrVersion", err)
	}
}

func TestClientRejectsWelcomeFromImpostorRelay(t *testing.T) {
	relayStatic, _ := GenerateKey()
	impostor, _ := GenerateKey()
	hs, _, _ := NewClientHello(relayStatic.PublicKey(), []byte("tok"))

	// An impostor without the relay's static key can still produce a
	// structurally valid welcome; the client must not accept it.
	_, impostorHello, _ := NewClientHello(impostor.PublicKey(), []byte("tok"))
	opened, err := OpenHello(impostor, impostorHello)
	if err != nil {
		t.Fatal(err)
	}
	_, welcome, _ := opened.Accept(impostor, Welcome{SessionID: 1})
	if _, _, err := hs.Finish(welcome); !errors.Is(err, ErrAuth) {
		t.Fatalf("impostor welcome err = %v, want ErrAuth", err)
	}
}

func TestRejectIsAuthenticatedAndTyped(t *testing.T) {
	relayStatic, _ := GenerateKey()
	hs, hello, _ := NewClientHello(relayStatic.PublicKey(), []byte("tok"))
	opened, _ := OpenHello(relayStatic, hello)

	_, _, err := hs.Finish(opened.Reject(RejectExpired))
	var rejected *RejectError
	if !errors.As(err, &rejected) || rejected.Code != RejectExpired {
		t.Fatalf("err = %v, want RejectError(expired)", err)
	}
	// A spoofed, unauthenticated reject must not be believed.
	if _, _, err := hs.Finish([]byte{TypeReject, RejectBadToken}); !errors.Is(err, ErrAuth) {
		t.Fatalf("spoofed reject err = %v, want ErrAuth", err)
	}
}

func TestReplayWindow(t *testing.T) {
	var w ReplayWindow
	if w.Mark(0) {
		t.Fatal("counter 0 must never be accepted")
	}
	for _, c := range []uint64{1, 2, 5} {
		if !w.Mark(c) {
			t.Fatalf("fresh counter %d rejected", c)
		}
	}
	if w.Mark(5) || w.Mark(1) {
		t.Fatal("duplicate accepted")
	}
	if !w.Mark(3) {
		t.Fatal("in-window late counter rejected")
	}
	if !w.Mark(5 + replayBits) {
		t.Fatal("big jump rejected")
	}
	if w.Mark(5) {
		t.Fatal("counter older than the window accepted")
	}
	// Counters that alias old ring slots after a jump must read as unseen.
	if !w.Mark(5 + replayBits - 1) {
		t.Fatal("in-window counter after a jump rejected (stale ring bit)")
	}
	if !w.Mark(3 * replayBits) {
		t.Fatal("jump of more than a window rejected")
	}
	if !w.Mark(3*replayBits - 7) {
		t.Fatal("counter within window after full reset rejected")
	}
}

func TestToken(t *testing.T) {
	secret := []byte("shared-secret")
	now := time.Unix(1_800_000_000, 0)
	signed, err := SignToken(secret, Token{UserID: "user-1", Device: "pc", Expires: now.Unix() + 60})
	if err != nil {
		t.Fatal(err)
	}
	got, err := VerifyToken(secret, signed, now)
	if err != nil || got.UserID != "user-1" || got.Device != "pc" {
		t.Fatalf("VerifyToken = %+v, %v", got, err)
	}
	if _, err := VerifyToken(secret, signed, now.Add(61*time.Second)); !errors.Is(err, ErrTokenExpired) {
		t.Fatalf("expired err = %v", err)
	}
	if _, err := VerifyToken([]byte("other"), signed, now); !errors.Is(err, ErrTokenSignature) {
		t.Fatalf("wrong secret err = %v", err)
	}
	forged := bytes.Clone(signed)
	forged[0] ^= 1
	if _, err := VerifyToken(secret, forged, now); !errors.Is(err, ErrTokenSignature) {
		t.Fatalf("forged err = %v", err)
	}
	if _, err := VerifyToken(secret, []byte("no-dot"), now); !errors.Is(err, ErrTokenFormat) {
		t.Fatalf("format err = %v", err)
	}
}

// The backend is written in Python and signs tokens with its own code. This
// is a token it produced (BoostX-Server tests pin the same string), so a
// format change on either side fails a test on that side.
func TestTokenFromBackendVerifies(t *testing.T) {
	secret := make([]byte, 32)
	for i := range secret {
		secret[i] = byte(i)
	}
	const signed = "eyJ1aWQiOiIxMTExMTExMS0yMjIyLTMzMzMtNDQ0NC01NTU1NTU1NTU1NTUiLCJkZXYiOiJkZXZpY2UtMSIsImV4cCI6NDEwMjQ0NDgwMH0" +
		".WULqx2cKjNC_Z75fRrCvSkJgo0J2iNRUWKR27huKZkA"

	token, err := VerifyToken(secret, []byte(signed), time.Unix(1_800_000_000, 0))
	if err != nil {
		t.Fatalf("backend-signed token rejected: %v", err)
	}
	want := Token{UserID: "11111111-2222-3333-4444-555555555555", Device: "device-1", Expires: 4_102_444_800}
	if token != want {
		t.Fatalf("claims = %+v, want %+v", token, want)
	}
	if _, err := VerifyToken(secret, []byte(signed), time.Unix(4_102_444_800, 0)); err != ErrTokenExpired {
		t.Fatalf("at its expiry time: %v, want expired", err)
	}
}
