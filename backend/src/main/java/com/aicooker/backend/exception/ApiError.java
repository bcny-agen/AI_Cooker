package com.aicooker.backend.exception;

import com.fasterxml.jackson.annotation.JsonInclude;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record ApiError(
        String code,
        String message,
        int status,
        String path,
        String operation
) {

    public ApiError(String code, String message, int status, String path) {
        this(code, message, status, path, null);
    }
}
