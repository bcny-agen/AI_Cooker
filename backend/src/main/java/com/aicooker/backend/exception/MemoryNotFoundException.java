package com.aicooker.backend.exception;

import java.util.UUID;

public class MemoryNotFoundException extends RuntimeException {

    public MemoryNotFoundException(UUID memoryId) {
        super("User memory was not found: " + memoryId);
    }
}
