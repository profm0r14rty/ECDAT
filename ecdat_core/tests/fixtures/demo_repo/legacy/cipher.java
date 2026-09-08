package com.example.legacy;

import javax.crypto.Cipher;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.util.Base64;

/**
 * Legacy symmetric encryption utility using the broken DES cipher.
 * Kept to represent deprecated infrastructure that ECDAT should flag.
 */
public final class CipherUtil {

    private CipherUtil() {
    }

    public static byte[] encrypt(byte[] plaintext, byte[] keyBytes) throws Exception {
        Cipher cipher = Cipher.getInstance("DES/ECB/PKCS5Padding");
        SecretKeySpec key = new SecretKeySpec(keyBytes, "DES");
        cipher.init(Cipher.ENCRYPT_MODE, key);
        return cipher.doFinal(plaintext);
    }

    public static String encryptToBase64(String plaintext, byte[] keyBytes) throws Exception {
        byte[] encrypted = encrypt(plaintext.getBytes(StandardCharsets.UTF_8), keyBytes);
        return Base64.getEncoder().encodeToString(encrypted);
    }
}
