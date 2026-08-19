package com.aicooker.backend.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record LoginRequest(
        @NotBlank(message = "username must not be blank")
        @Size(max = 50, message = "username must contain at most 50 characters")
        String username,
        @NotBlank(message = "password must not be blank")
        @Size(max = 64, message = "password must contain at most 64 characters")
        String password
) {
}
