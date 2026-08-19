package com.aicooker.backend.dto;

import java.util.UUID;
import java.util.List;

public record ChatResponse(
        UUID conversationId,
        String answer,
        List<GeneratedImageResponse> generatedImages
) {
    public ChatResponse(UUID conversationId, String answer) {
        this(conversationId, answer, List.of());
    }
}
