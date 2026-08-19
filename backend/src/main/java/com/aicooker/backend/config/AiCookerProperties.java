package com.aicooker.backend.config;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "ai.cooker")
public record AiCookerProperties(
        URI baseUrl,
        Duration connectTimeout,
        Duration readTimeout
) {

    public AiCookerProperties {
        if (baseUrl == null
                || baseUrl.getHost() == null
                || !("http".equalsIgnoreCase(baseUrl.getScheme())
                || "https".equalsIgnoreCase(baseUrl.getScheme()))) {
            throw new IllegalArgumentException(
                    "ai.cooker.base-url must be an absolute HTTP or HTTPS URL"
            );
        }
        requirePositive(connectTimeout, "ai.cooker.connect-timeout");
        requirePositive(readTimeout, "ai.cooker.read-timeout");
    }

    private static void requirePositive(Duration duration, String propertyName) {
        if (duration == null || duration.isZero() || duration.isNegative()) {
            throw new IllegalArgumentException(propertyName + " must be positive");
        }
    }
}
