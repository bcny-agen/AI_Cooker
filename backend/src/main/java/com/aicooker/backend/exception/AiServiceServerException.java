package com.aicooker.backend.exception;

public class AiServiceServerException extends AiServiceException {

    public AiServiceServerException(String message) {
        super(message);
    }

    public AiServiceServerException(String message, Throwable cause) {
        super(message, cause);
    }
}
