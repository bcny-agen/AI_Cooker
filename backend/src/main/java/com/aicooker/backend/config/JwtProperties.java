package com.aicooker.backend.config;

import java.nio.charset.StandardCharsets;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "security.jwt")
public record JwtProperties(
        String secret,
        String issuer,
        Duration ttl
) {

    public JwtProperties {
        if (secret == null
                || secret.getBytes(StandardCharsets.UTF_8).length < 32) {
            throw new IllegalArgumentException(
                    "security.jwt.secret must contain at least 32 UTF-8 bytes"
            );
        }
        if (issuer == null || issuer.isBlank()) {
            throw new IllegalArgumentException(
                    "security.jwt.issuer must not be blank"
            );
        }
        if (ttl == null || ttl.isZero() || ttl.isNegative()) {
            throw new IllegalArgumentException(
                    "security.jwt.ttl must be positive"
            );
        }
    }
}
