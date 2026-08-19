package com.aicooker.backend.dto;

import com.aicooker.backend.entity.ModelId;
import jakarta.validation.constraints.NotNull;

public record ChangeConversationModelRequest(
        @NotNull(message = "modelId must not be null") ModelId modelId
) {
}
