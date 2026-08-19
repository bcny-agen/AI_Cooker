package com.aicooker.backend.exception;

public class AiServiceUnavailableException extends AiServiceException {

    public AiServiceUnavailableException(Throwable cause) {
        super("The Python AI service is unavailable.", cause);
    }
}
