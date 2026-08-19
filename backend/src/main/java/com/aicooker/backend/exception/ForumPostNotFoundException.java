package com.aicooker.backend.exception;

import java.util.UUID;

public class ForumPostNotFoundException extends RuntimeException {

    public ForumPostNotFoundException(UUID postId) {
        super("Forum post was not found: " + postId);
    }
}
