package com.aicooker.backend.exception;

import java.util.UUID;

public class GeneratedImageNotFoundException extends RuntimeException {

    public GeneratedImageNotFoundException(UUID imageId) {
        super("Generated image not found: " + imageId);
    }
}
