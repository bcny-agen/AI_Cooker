package com.aicooker.backend.dto;

import java.util.UUID;

import com.fasterxml.jackson.annotation.JsonInclude;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record ChatStreamEvent(
        String type,
        UUID conversationId,
        String stage,
        String message,
        String content,
        GeneratedImageResponse generatedImage
) {

    public ChatStreamEvent(
            String type,
            UUID conversationId,
            String stage,
            String message,
            String content
    ) {
        this(type, conversationId, stage, message, content, null);
    }

    public static ChatStreamEvent status(
            UUID conversationId,
            String stage,
            String message
    ) {
        return new ChatStreamEvent(
                "status",
                conversationId,
                stage,
                message,
                null,
                null
        );
    }

    public static ChatStreamEvent token(UUID conversationId, String content) {
        return new ChatStreamEvent(
                "token",
                conversationId,
                null,
                null,
                content,
                null
        );
    }

    public static ChatStreamEvent generatedImage(
            UUID conversationId,
            GeneratedImageResponse image
    ) {
        return new ChatStreamEvent(
                "generated_image",
                conversationId,
                null,
                null,
                null,
                image
        );
    }

    public static ChatStreamEvent imageError(UUID conversationId) {
        return new ChatStreamEvent(
                "image_error",
                conversationId,
                null,
                "Image generation failed. You can retry this request.",
                null,
                null
        );
    }

    public static ChatStreamEvent done(UUID conversationId) {
        return new ChatStreamEvent(
                "done",
                conversationId,
                null,
                null,
                null,
                null
        );
    }

    public static ChatStreamEvent error(UUID conversationId) {
        return new ChatStreamEvent(
                "error",
                conversationId,
                null,
                "AI Cooker could not complete the response. Please try again.",
                null,
                null
        );
    }
}
