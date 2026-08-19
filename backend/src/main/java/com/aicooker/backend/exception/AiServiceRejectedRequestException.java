package com.aicooker.backend.exception;

public class AiServiceRejectedRequestException extends AiServiceException {

    public AiServiceRejectedRequestException(Throwable cause) {
        super("The Python AI service rejected the request.", cause);
    }
}
