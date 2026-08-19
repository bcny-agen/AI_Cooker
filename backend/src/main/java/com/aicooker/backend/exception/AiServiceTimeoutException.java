package com.aicooker.backend.exception;

public class AiServiceTimeoutException extends AiServiceException {

    public AiServiceTimeoutException(Throwable cause) {
        super("The Python AI service timed out.", cause);
    }
}
