package com.aicooker.backend.dto;

import java.util.UUID;

import com.aicooker.backend.entity.ModelId;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record ChatRequest(
        UUID conversationId,
        @NotBlank(message = "message must not be blank")
        @Size(max = 20_000, message = "message must contain at most 20000 characters")
        String message,
        UUID imageId,
        ModelId modelId
) {
    public ChatRequest(UUID conversationId, String message, UUID imageId) {
        this(conversationId, message, imageId, null);
    }
}
