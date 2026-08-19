package com.aicooker.backend.exception;

public class AiThreadRecoveryRequiredException extends AiServiceException {

    public AiThreadRecoveryRequiredException(Throwable cause) {
        super("The Python Agent thread requires one-time recovery.", cause);
    }
}
