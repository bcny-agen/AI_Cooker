package com.aicooker.backend.dto;

import java.time.Instant;
import java.util.UUID;

import com.aicooker.backend.entity.ModelId;

public record ConversationResponse(
        UUID id,
        String title,
        ModelId modelId,
        Instant createdAt,
        Instant updatedAt
) {
    public ConversationResponse(
            UUID id,
            String title,
            Instant createdAt,
            Instant updatedAt
    ) {
        this(id, title, ModelId.STEP_FLASH_3_7, createdAt, updatedAt);
    }
}
