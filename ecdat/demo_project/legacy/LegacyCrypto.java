package com.showcase.legacy;

import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.DESedeKeySpec;
import java.security.Key;
import java.security.MessageDigest;
import java.util.Base64;

/**
 * Legacy cryptographic utilities — retained for backward compatibility
 * with old client SDKs that still use 3DES and MD5-based checksums.
 *
 * Both algorithms are broken or deprecated and must be replaced:
 * - 3DES: 112-bit effective key, slow, NIST retired in 2023.
 * - MD5:  collision attacks demonstrated, unsuitable for security use.
 */
public final class LegacyCrypto {

    private static final String DES_EDE_CIPHER = "DESede/ECB/PKCS5Padding";

    private LegacyCrypto() {}

    /**
     * Encrypt data with Triple DES (3DES).
     *
     * @param plaintext data to encrypt
     * @param keyBytes  24-byte (192-bit) 3DES key
     * @return Base64-encoded ciphertext
     */
    public static String encrypt3DES(String plaintext, byte[] keyBytes)
            throws Exception {
        DESedeKeySpec spec = new DESedeKeySpec(keyBytes);
        Key key = javax.crypto.SecretKeyFactory.getInstance("DESede")
                .generateSecret(spec);

        Cipher cipher = Cipher.getInstance(DES_EDE_CIPHER);
        cipher.init(Cipher.ENCRYPT_MODE, key);
        byte[] ct = cipher.doFinal(plaintext.getBytes("UTF-8"));
        return Base64.getEncoder().encodeToString(ct);
    }

    /**
     * Generate a random 3DES key.
     */
    public static SecretKey generate3DESKey() throws Exception {
        KeyGenerator kg = KeyGenerator.getInstance("DESede");
        kg.init(168); // 168-bit key, 112-bit effective security
        return kg.generateKey();
    }

    /**
     * Compute an MD5 digest of the input bytes.
     *
     * @deprecated Use SHA-256 instead. MD5 has broken collision resistance.
     */
    @Deprecated
    public static String md5Checksum(byte[] data) throws Exception {
        MessageDigest md = MessageDigest.getInstance("MD5");
        byte[] digest = md.digest(data);
        StringBuilder sb = new StringBuilder();
        for (byte b : digest) {
            sb.append(String.format("%02x", b));
        }
        return sb.toString();
    }

    /**
     * Compute an MD5 hash of a string (used by legacy credential store).
     */
    @Deprecated
    public static String legacyCredentialHash(String credential) throws Exception {
        MessageDigest md = MessageDigest.getInstance("MD5");
        byte[] raw = md.digest(credential.getBytes("UTF-8"));
        return Base64.getEncoder().encodeToString(raw);
    }
}
