package com.aicooker.backend.exception;

public class PasswordTooLongException extends RuntimeException {

    public PasswordTooLongException() {
        super("The password exceeds BCrypt's safe UTF-8 byte limit.");
    }
}
