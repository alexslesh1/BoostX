package engine

import (
	"crypto/subtle"
	"encoding/json"
	"errors"
	"net/http"
	"sync"
	"time"
)

// StartConfig is everything needed to bring the engine up: where the relay
// is, how to authenticate to it, and which programs to route through it.
type StartConfig struct {
	Relay          string `json:"relay"`
	RelayPublicKey string `json:"relay_public_key"`
	Token          string `json:"token"`
	Rules          []Rule `json:"rules"`
}

func (c StartConfig) validate() error {
	switch {
	case c.Relay == "":
		return errors.New("relay is required")
	case c.RelayPublicKey == "":
		return errors.New("relay_public_key is required")
	case c.Token == "":
		return errors.New("token is required")
	case len(c.Rules) == 0:
		return errors.New("at least one rule is required")
	}
	return nil
}

// Factory builds a ready-to-run engine; the platform supplies it.
type Factory func(StartConfig) (*Engine, error)

// Controller owns at most one running engine and exposes it over a small
// local HTTP API, so any UI (whatever it is written in) can drive it without
// itself needing administrator rights.
type Controller struct {
	factory Factory
	key     string

	mu      sync.Mutex
	engine  *Engine
	lastErr string
}

// NewController requires every request to carry key in X-Nexora-Key. A web
// page in the user's browser can reach 127.0.0.1 but cannot know the key.
func NewController(factory Factory, key string) *Controller {
	return &Controller{factory: factory, key: key}
}

func (c *Controller) Start(cfg StartConfig) error {
	if err := cfg.validate(); err != nil {
		return err
	}
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.engine != nil {
		c.engine.Close()
		c.engine = nil
	}
	eng, err := c.factory(cfg)
	if err != nil {
		c.lastErr = err.Error()
		return err
	}
	c.engine = eng
	c.lastErr = ""
	go func() {
		err := eng.Run()
		c.mu.Lock()
		defer c.mu.Unlock()
		if c.engine == eng {
			c.engine = nil
			if err != nil {
				c.lastErr = err.Error()
			}
		}
	}()
	return nil
}

func (c *Controller) Stop() {
	c.mu.Lock()
	eng := c.engine
	c.engine = nil
	c.mu.Unlock()
	if eng != nil {
		eng.Close()
	}
}

type statusResponse struct {
	Running bool   `json:"running"`
	Error   string `json:"error,omitempty"`
	*Status
}

func (c *Controller) status() statusResponse {
	c.mu.Lock()
	eng, lastErr := c.engine, c.lastErr
	c.mu.Unlock()
	response := statusResponse{Running: eng != nil, Error: lastErr}
	if eng != nil {
		status := eng.Status()
		response.Status = &status
	}
	return response
}

func writeJSON(w http.ResponseWriter, code int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	json.NewEncoder(w).Encode(body)
}

func writeError(w http.ResponseWriter, code int, message string) {
	writeJSON(w, code, map[string]string{"error": message})
}

// Handler is the local control API:
//
//	GET  /v1/status
//	POST /v1/start   StartConfig
//	POST /v1/stop
//	POST /v1/probe   {"relays": ["host:port", ...]}
func (c *Controller) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /v1/status", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, c.status())
	})
	mux.HandleFunc("POST /v1/start", func(w http.ResponseWriter, r *http.Request) {
		var cfg StartConfig
		if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1<<20)).Decode(&cfg); err != nil {
			writeError(w, http.StatusBadRequest, "invalid JSON body")
			return
		}
		if err := cfg.validate(); err != nil {
			writeError(w, http.StatusBadRequest, err.Error())
			return
		}
		if err := c.Start(cfg); err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		writeJSON(w, http.StatusOK, c.status())
	})
	mux.HandleFunc("POST /v1/stop", func(w http.ResponseWriter, r *http.Request) {
		c.Stop()
		writeJSON(w, http.StatusOK, c.status())
	})
	mux.HandleFunc("POST /v1/probe", func(w http.ResponseWriter, r *http.Request) {
		var request struct {
			Relays []string `json:"relays"`
		}
		if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1<<16)).Decode(&request); err != nil || len(request.Relays) == 0 || len(request.Relays) > 64 {
			writeError(w, http.StatusBadRequest, "body must be {\"relays\": [1..64 addresses]}")
			return
		}
		writeJSON(w, http.StatusOK, Probe(request.Relays, 4, 800*time.Millisecond))
	})

	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if subtle.ConstantTimeCompare([]byte(r.Header.Get("X-Nexora-Key")), []byte(c.key)) != 1 {
			writeError(w, http.StatusUnauthorized, "missing or wrong X-Nexora-Key")
			return
		}
		mux.ServeHTTP(w, r)
	})
}
