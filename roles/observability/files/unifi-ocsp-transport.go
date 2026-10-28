// Compiled into the exact github.com/unpoller/unifi/v5 source dependency.
package unifi

import (
	"bytes"
	"context"
	"crypto/tls"
	"crypto/x509"
	"encoding/base64"
	"encoding/json"
	"errors"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"time"
)

func iopOCSPEnabled() bool { return os.Getenv("IOP_UNIFI_OCSP_POLICY") != "" }

func iopOCSPGuard(config *Config) error {
	if !iopOCSPEnabled() {
		return nil
	}
	origin, err := url.Parse(config.URL)
	if err != nil || origin.Scheme != "https" || origin.Hostname() == "" || origin.User != nil ||
		!config.VerifySSL || len(config.SSLCert) != 0 {
		return errors.New("unifi_ocsp_config")
	}
	if net.ParseIP(os.Getenv("IOP_UNIFI_OCSP_CONTROLLER_ADDRESS")) == nil {
		return errors.New("unifi_ocsp_config")
	}
	for _, name := range []string{"IOP_UNIFI_OCSP_POLICY", "IOP_UNIFI_OCSP_PYTHON", "IOP_UNIFI_OCSP_VERIFIER", "IOP_UNIFI_OCSP_CA_FILE"} {
		path := os.Getenv(name)
		if !filepath.IsAbs(path) {
			return errors.New("unifi_ocsp_config")
		}
		if _, err := os.Stat(path); err != nil {
			return errors.New("unifi_ocsp_config")
		}
	}
	roots := x509.NewCertPool()
	pem, err := os.ReadFile(os.Getenv("IOP_UNIFI_OCSP_CA_FILE"))
	if err != nil || !roots.AppendCertsFromPEM(pem) {
		return errors.New("unifi_ocsp_config")
	}
	return nil
}

type iopOCSPRoundTripper struct{ transport *http.Transport }

func (t *iopOCSPRoundTripper) CloseIdleConnections() { t.transport.CloseIdleConnections() }

func (t *iopOCSPRoundTripper) RoundTrip(request *http.Request) (*http.Response, error) {
	response, err := t.transport.RoundTrip(request)
	var certificateError *tls.CertificateVerificationError
	if err != nil && errors.As(err, &certificateError) {
		ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer cancel()
		command := exec.CommandContext(ctx, os.Getenv("IOP_UNIFI_OCSP_PYTHON"), os.Getenv("IOP_UNIFI_OCSP_VERIFIER"), os.Getenv("IOP_UNIFI_OCSP_POLICY"))
		command.Stdin = bytes.NewBufferString(`{"tls_failure":true}`)
		_ = command.Run() // Reporting failure must never relax the original TLS denial.
		return nil, errors.New("unifi_ocsp_tls")
	}
	return response, err
}

func iopOCSPTransport(origin string) http.RoundTripper {
	endpoint, _ := url.Parse(origin)
	expectedPort := endpoint.Port()
	if expectedPort == "" {
		expectedPort = "443"
	}
	roots, err := x509.SystemCertPool()
	if err != nil {
		roots = x509.NewCertPool()
	}
	pem, _ := os.ReadFile(os.Getenv("IOP_UNIFI_OCSP_CA_FILE"))
	roots.AppendCertsFromPEM(pem) // Parsing failure is rejected by iopOCSPGuard.
	transport := &http.Transport{
		DialContext: func(ctx context.Context, network, target string) (net.Conn, error) {
			host, port, err := net.SplitHostPort(target)
			if err != nil || host != endpoint.Hostname() || port != expectedPort {
				return nil, errors.New("unifi_ocsp_destination")
			}
			dialer := net.Dialer{Timeout: 5 * time.Second}
			return dialer.DialContext(ctx, network, net.JoinHostPort(os.Getenv("IOP_UNIFI_OCSP_CONTROLLER_ADDRESS"), port))
		},
		DisableKeepAlives:     true,
		ForceAttemptHTTP2:     false,
		TLSNextProto:          map[string]func(string, *tls.Conn) http.RoundTripper{},
		TLSHandshakeTimeout:   15 * time.Second,
		ResponseHeaderTimeout: 15 * time.Second,
		TLSClientConfig: &tls.Config{
			MinVersion:             tls.VersionTLS12,
			RootCAs:                roots,
			SessionTicketsDisabled: true,
			VerifyConnection: func(state tls.ConnectionState) error {
				if state.DidResume || len(state.VerifiedChains) == 0 || len(state.PeerCertificates) == 0 {
					return errors.New("unifi_ocsp_tls")
				}
				ctx, cancel := context.WithTimeout(context.Background(), 12*time.Second)
				defer cancel()
				payload, _ := json.Marshal(map[string]string{"leaf": base64.StdEncoding.EncodeToString(state.PeerCertificates[0].Raw)})
				command := exec.CommandContext(ctx, os.Getenv("IOP_UNIFI_OCSP_PYTHON"), os.Getenv("IOP_UNIFI_OCSP_VERIFIER"), os.Getenv("IOP_UNIFI_OCSP_POLICY"))
				command.Stdin = bytes.NewReader(payload)
				// Verifier emits one bounded fixed-schema line. It never receives credentials.
				var output bytes.Buffer
				command.Stdout = &output
				err := command.Run()
				var result struct {
					OK     bool   `json:"ok"`
					Reason string `json:"reason"`
				}
				if output.Len() > 1024 || json.Unmarshal(output.Bytes(), &result) != nil {
					return errors.New("unifi_ocsp_internal")
				}
				if err != nil || !result.OK {
					allowed := map[string]bool{"tls": true, "revoked": true, "unknown": true, "signature": true, "responder": true,
						"identity": true, "time": true, "timeout": true, "http": true, "malformed": true, "cache_expired": true,
						"unavailable": true, "clock": true, "state": true, "config": true, "internal": true}
					if !allowed[result.Reason] {
						return errors.New("unifi_ocsp_internal")
					}
					return errors.New("unifi_ocsp_" + result.Reason)
				}
				return nil
			},
		},
	}
	return &iopOCSPRoundTripper{transport: transport}
}

func iopOCSPClient(client *http.Client, origin string) {
	if !iopOCSPEnabled() {
		return
	}
	client.Transport = iopOCSPTransport(origin)
	client.Timeout = 30 * time.Second
	client.CheckRedirect = func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse }
}
