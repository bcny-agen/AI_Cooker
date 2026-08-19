package com.aicooker.backend.dto;

import java.time.Instant;
import java.util.UUID;

import com.aicooker.backend.entity.MemoryType;

public record MemoryResponse(
        UUID id,
        MemoryType memoryType,
        String key,
        String value,
        Instant createdAt,
        Instant updatedAt
) {
}
