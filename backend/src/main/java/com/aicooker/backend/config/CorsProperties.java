package com.aicooker.backend.config;

import java.net.URI;
import java.util.List;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.cors")
public record CorsProperties(List<String> allowedOrigins) {

    public CorsProperties {
        if (allowedOrigins == null || allowedOrigins.isEmpty()) {
            throw new IllegalArgumentException(
                    "app.cors.allowed-origins must contain at least one origin"
            );
        }
        allowedOrigins = allowedOrigins.stream()
                .map(String::trim)
                .peek(CorsProperties::validateOrigin)
                .toList();
    }

    private static void validateOrigin(String value) {
        URI uri;
        try {
            uri = URI.create(value);
        } catch (IllegalArgumentException exception) {
            throw new IllegalArgumentException(
                    "Invalid CORS origin: " + value,
                    exception
            );
        }
        if (uri.getHost() == null
                || !("http".equalsIgnoreCase(uri.getScheme())
                || "https".equalsIgnoreCase(uri.getScheme()))
                || (uri.getPath() != null && !uri.getPath().isEmpty())
                || uri.getQuery() != null
                || uri.getFragment() != null) {
            throw new IllegalArgumentException(
                    "CORS origins must be absolute HTTP(S) origins without paths"
            );
        }
    }
}
