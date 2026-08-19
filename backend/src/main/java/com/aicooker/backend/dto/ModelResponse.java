package com.aicooker.backend.dto;

import com.aicooker.backend.entity.ModelId;

public record ModelResponse(
        ModelId id,
        String displayName,
        boolean supportsText,
        boolean supportsTools,
        boolean supportsStreaming,
        boolean supportsImages,
        boolean available
) {
}
