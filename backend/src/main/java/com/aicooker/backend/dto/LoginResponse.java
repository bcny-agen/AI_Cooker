package com.aicooker.backend.dto;

public record LoginResponse(
        String token,
        long expiresIn
) {
}
