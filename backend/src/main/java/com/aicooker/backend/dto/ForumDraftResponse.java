package com.aicooker.backend.dto;

import java.util.UUID;

import com.aicooker.backend.entity.ForumImageType;
import com.aicooker.backend.entity.ModelId;

public record ForumDraftResponse(
        UUID sourceConversationId,
        String title,
        String content,
        String dishName,
        UUID suggestedImageId,
        ForumImageType suggestedImageType,
        ModelId modelId
) {
}
