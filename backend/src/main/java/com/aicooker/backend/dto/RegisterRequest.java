package com.aicooker.backend.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record RegisterRequest(
        @NotBlank(message = "username must not be blank")
        @Size(min = 3, max = 50, message = "username must contain 3 to 50 characters")
        @Pattern(
                regexp = "^[A-Za-z0-9][A-Za-z0-9_.-]*$",
                message = "username contains unsupported characters"
        )
        String username,
        @NotBlank(message = "password must not be blank")
        @Size(min = 8, max = 64, message = "password must contain 8 to 64 characters")
        String password
) {
}
