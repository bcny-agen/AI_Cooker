package com.aicooker.backend.dto;

import com.aicooker.backend.entity.MemoryType;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record UpdateMemoryRequest(
        @NotNull MemoryType memoryType,
        @NotBlank @Size(max = 80) String key,
        @NotBlank @Size(max = 255) String value
) {
}
