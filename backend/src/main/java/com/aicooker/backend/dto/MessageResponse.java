package com.aicooker.backend.dto;

import java.time.Instant;
import java.util.UUID;
import java.util.List;

import com.aicooker.backend.entity.MessageRole;

public record MessageResponse(
        Long id,
        MessageRole role,
        String content,
        UUID imageId,
        Instant createdAt,
        List<GeneratedImageResponse> generatedImages
) {
    public MessageResponse(
            Long id,
            MessageRole role,
            String content,
            UUID imageId,
            Instant createdAt
    ) {
        this(id, role, content, imageId, createdAt, List.of());
    }
}
