package com.aicooker.backend.exception;

public class InsufficientConversationException extends RuntimeException {

    public InsufficientConversationException() {
        super("The conversation does not contain enough visible history.");
    }
}
