package com.aicooker.backend.exception;

import java.util.UUID;

public class ForumPostImageNotFoundException extends RuntimeException {

    public ForumPostImageNotFoundException(UUID postId) {
        super("Forum post does not have a visible image: " + postId);
    }
}
