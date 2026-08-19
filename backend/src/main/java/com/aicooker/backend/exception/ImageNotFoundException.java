package com.aicooker.backend.exception;

import java.util.UUID;

public class ImageNotFoundException extends RuntimeException {

    public ImageNotFoundException(UUID imageId) {
        super("Image not found: " + imageId);
    }
}
