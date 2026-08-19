package com.aicooker.backend.dto;

import java.time.Instant;
import java.util.UUID;

public record GeneratedImageResponse(
        UUID imageId,
        String url,
        String imageModel,
        Instant createdAt
) {
}
