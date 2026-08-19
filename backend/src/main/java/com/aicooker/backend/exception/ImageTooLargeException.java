package com.aicooker.backend.exception;

public class ImageTooLargeException extends RuntimeException {

    public ImageTooLargeException() {
        super("The image exceeds the configured maximum size.");
    }
}
