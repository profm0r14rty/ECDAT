// Package keyexchange implements Diffie-Hellman key agreement for the
// secure inter-service communication channel.
//
// WARNING: Classic DH with 2048-bit prime is quantum-vulnerable.
// This module is scheduled for ML-KEM migration before production launch.
package keyexchange

import (
	"crypto/dh"
	"fmt"
	"math/big"
)

// Group14 is the 2048-bit MODP group from RFC 3526 (Group 14).
var Group14 *dh.Group

// DHParams holds the parameters for a Diffie-Hellman key exchange.
type DHParams struct {
	Prime     *big.Int
	Generator int64
}

// GenerateKeyPair creates a new DH key pair using Group 14.
// Returns (privateKey, publicKey) as byte slices.
func GenerateKeyPair() ([]byte, []byte, error) {
	privKey, err := dh.GenerateKey(Group14)
	if err != nil {
		return nil, nil, fmt.Errorf("DH key generation failed: %w", err)
	}
	pubKey := Group14.PublicKey(privKey)
	return privKey, pubKey.Bytes(), nil
}

// ComputeSharedSecret derives the shared secret from a private key
// and the peer's public key.
func ComputeSharedSecret(privKey *dh.PrivateKey, peerPubKey *dh.PublicKey) []byte {
	return privKey.PublicKey().SharedKey(peerPubKey)
}

// GenerateDHKey is a convenience wrapper that generates and returns
// just the private key bytes (useful for single-key contexts).
func GenerateDHKey() ([]byte, error) {
	privKey, err := dh.GenerateKey(Group14)
	if err != nil {
		return nil, err
	}
	return privKey.PublicKey().Bytes(), nil
}
