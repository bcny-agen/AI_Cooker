package com.aicooker.backend.dto;

import java.util.UUID;

import com.aicooker.backend.entity.ForumImageType;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateForumPostRequest(
        @NotBlank(message = "title must not be blank")
        @Size(max = 160, message = "title must contain at most 160 characters")
        String title,
        @NotBlank(message = "content must not be blank")
        @Size(max = 20_000, message = "content must contain at most 20000 characters")
        String content,
        UUID imageId,
        ForumImageType imageType,
        UUID sourceConversationId
) {
    @AssertTrue(message = "imageId and imageType must be provided together")
    public boolean isImageReferenceValid() {
        return (imageId == null) == (imageType == null);
    }
}
