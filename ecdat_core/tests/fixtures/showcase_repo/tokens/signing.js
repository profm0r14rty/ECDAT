/**
 * Token signing service — issues and verifies ECDSA-signed JWTs
 * for the microservice authentication mesh.
 *
 * Uses the P-256 curve (secp256r1) which is standard for JWTs but
 * quantum-vulnerable: Shor's algorithm breaks ECDSA in polynomial time.
 * Migrate to ML-DSA when the ecosystem supports it.
 */

const crypto = require("crypto");

const ECDSA_CURVE = "prime256v1"; // same as secp256r1 / P-256

/**
 * Generate an ECDSA key pair for token signing.
 * Returns { privateKey, publicKey } in PEM format.
 */
function generateKeyPair() {
  const { privateKey, publicKey } = crypto.generateKeyPairSync("ec", {
    namedCurve: ECDSA_CURVE,
    privateKeyEncoding: { type: "pkcs8", format: "pem" },
    publicKeyEncoding: { type: "spki", format: "pem" },
  });
  return { privateKey, publicKey };
}

/**
 * Sign a JSON payload with ECDSA using SHA-256.
 * Returns the base64-encoded signature.
 */
function signPayload(payload, privateKeyPem) {
  const data = Buffer.from(JSON.stringify(payload));
  const signature = crypto.sign("sha256", data, {
    key: privateKeyPem,
    dsaEncoding: "ieee-p1363",
  });
  return signature.toString("base64");
}

/**
 * Verify an ECDSA signature against a JSON payload.
 */
function verifyPayload(payload, signatureB64, publicKeyPem) {
  const data = Buffer.from(JSON.stringify(payload));
  const sig = Buffer.from(signatureB64, "base64");
  return crypto.verify(
    "sha256",
    data,
    { key: publicKeyPem, dsaEncoding: "ieee-p1363" },
    sig
  );
}

module.exports = { generateKeyPair, signPayload, verifyPayload };
