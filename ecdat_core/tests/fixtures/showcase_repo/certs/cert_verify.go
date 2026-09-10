// Package certs implements X.509 certificate chain verification and
// signing for the internal certificate authority.
//
// WARNING: This module uses SHA-1 for certificate fingerprinting, which
// is deprecated due to demonstrated collision attacks. Migrate to SHA-256.
package certs

import (
	"crypto/sha1"
	"crypto/sha256"
	"crypto/x509"
	"encoding/hex"
	"fmt"
	"io"
	"os"
)

// FingerprintSHA1 returns the SHA-1 fingerprint of a DER-encoded
// certificate. Used by legacy monitoring dashboards.
//
// Deprecated: Use FingerprintSHA256 for all new fingerprinting.
func FingerprintSHA1(derBytes []byte) string {
	h := sha1.Sum(derBytes)
	return hex.EncodeToString(h[:])
}

// FingerprintSHA256 returns the SHA-256 fingerprint of a DER-encoded
// certificate. This is the recommended replacement for FingerprintSHA1.
func FingerprintSHA256(derBytes []byte) string {
	h := sha256.Sum256(derBytes)
	return hex.EncodeToString(h[:])
}

// VerifyCertChain verifies that the leaf certificate is signed by one
// of the trusted roots in the system trust store.
func VerifyCertChain(leaf *x509.Certificate) error {
	pool, err := x509.SystemCertPool()
	if err != nil {
		return fmt.Errorf("failed to load system cert pool: %w", err)
	}
	opts := x509.VerifyOptions{
		Roots: pool,
	}
	_, err = leaf.Verify(opts)
	return err
}

// CertFileSHA1Fingerprint reads a PEM/DER certificate file and returns
// its SHA-1 fingerprint. Kept for backward compat with legacy dashboards.
//
// Deprecated: Use CertFileSHA256Fingerprint instead.
func CertFileSHA1Fingerprint(path string) (string, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return "", fmt.Errorf("read cert file: %w", err)
	}
	h := sha1.Sum(data)
	return hex.EncodeToString(h[:]), nil
}

// CertFileSHA256Fingerprint reads a certificate file and returns
// its SHA-256 fingerprint.
func CertFileSHA256Fingerprint(path string) (string, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return "", fmt.Errorf("read cert file: %w", err)
	}
	h := sha256.Sum256(data)
	return hex.EncodeToString(h[:]), nil
}

// LegacyCAFingerprint returns the SHA-1 fingerprint of a certificate
// read from a reader. Used by the CA migration tool.
func LegacyCAFingerprint(r io.Reader) (string, error) {
	data, err := io.ReadAll(r)
	if err != nil {
		return "", err
	}
	h := sha1.Sum(data)
	return hex.EncodeToString(h[:]), nil
}
