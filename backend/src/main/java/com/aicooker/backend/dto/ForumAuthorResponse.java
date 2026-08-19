package com.aicooker.backend.dto;

import java.util.UUID;

public record ForumAuthorResponse(
        UUID id,
        String username
) {
}
