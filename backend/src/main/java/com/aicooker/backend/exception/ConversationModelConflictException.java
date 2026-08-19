package com.aicooker.backend.exception;

public class ConversationModelConflictException extends RuntimeException {

    public ConversationModelConflictException() {
        super("Use the explicit model-switch endpoint for an existing conversation.");
    }
}
