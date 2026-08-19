package com.aicooker.backend.exception;

public class InvalidLoginException extends RuntimeException {

    public InvalidLoginException() {
        super("Invalid username or password.");
    }
}
