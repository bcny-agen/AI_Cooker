package com.aicooker.backend.dto;

import java.util.UUID;

public record ImageResponse(
        UUID imageId,
        String url,
        String originalFilename,
        String contentType,
        long size
) {
}
