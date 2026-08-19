package com.aicooker.backend.exception;

public abstract class AiServiceException extends RuntimeException {

    protected AiServiceException(String message) {
        super(message);
    }

    protected AiServiceException(String message, Throwable cause) {
        super(message, cause);
    }
}
