package com.aicooker.backend.service;

import org.springframework.stereotype.Component;

@Component
public class ConversationTitleGenerator {

    static final int MAX_TITLE_CODE_POINTS = 60;

    public String generate(String firstUserMessage) {
        if (firstUserMessage == null || firstUserMessage.isBlank()) {
            return "New conversation";
        }

        String normalized = firstUserMessage.strip().replaceAll("\\s+", " ");
        int codePointCount = normalized.codePointCount(0, normalized.length());
        if (codePointCount <= MAX_TITLE_CODE_POINTS) {
            return normalized;
        }

        int endIndex = normalized.offsetByCodePoints(
                0,
                MAX_TITLE_CODE_POINTS - 1
        );
        return normalized.substring(0, endIndex) + "…";
    }
}
