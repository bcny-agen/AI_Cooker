package com.aicooker.backend.dto;

import java.time.Instant;
import java.util.UUID;

import com.aicooker.backend.entity.ForumImageType;

public record ForumPostResponse(
        UUID id,
        String title,
        String content,
        ForumAuthorResponse author,
        UUID imageId,
        ForumImageType imageType,
        Instant createdAt,
        Instant updatedAt,
        boolean isOwner
) {
}
