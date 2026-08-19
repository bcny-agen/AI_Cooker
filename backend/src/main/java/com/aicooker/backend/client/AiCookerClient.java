package com.aicooker.backend.client;

import java.util.List;
import java.util.UUID;
import java.util.function.Consumer;

import com.aicooker.backend.entity.ModelId;
import com.aicooker.backend.entity.MemoryType;

public interface AiCookerClient {

    default ChatResult chat(
            UUID conversationId,
            String message,
            String imageUrl
    ) {
        return chat(conversationId, message, imageUrl, ModelId.STEP_FLASH_3_7);
    }

    default ChatResult chat(
            UUID conversationId,
            String message,
            String imageUrl,
            ModelId modelId
    ) {
        return chat(
                conversationId,
                message,
                imageUrl,
                modelId,
                List.of(),
                false
        );
    }

    default ChatResult chat(
            UUID conversationId,
            String message,
            String imageUrl,
            ModelId modelId,
            List<String> userMemories
    ) {
        return chat(
                conversationId,
                message,
                imageUrl,
                modelId,
                userMemories,
                false
        );
    }

    ChatResult chat(
            UUID conversationId,
            String message,
            String imageUrl,
            ModelId modelId,
            List<String> userMemories,
            boolean continuationExpected
    );

    ChatResult recoverChat(
            UUID conversationId,
            String message,
            String imageUrl,
            ModelId modelId,
            List<String> userMemories,
            List<RecoveryMessage> recoveryHistory
    );

    default void streamChat(
            UUID conversationId,
            String message,
            String imageUrl,
            ModelId modelId,
            Consumer<StreamEvent> eventConsumer
    ) {
        streamChat(
                conversationId,
                message,
                imageUrl,
                modelId,
                List.of(),
                eventConsumer
        );
    }

    default void streamChat(
            UUID conversationId,
            String message,
            String imageUrl,
            ModelId modelId,
            List<String> userMemories,
            Consumer<StreamEvent> eventConsumer
    ) {
        streamChat(
                conversationId,
                message,
                imageUrl,
                modelId,
                userMemories,
                false,
                eventConsumer
        );
    }

    void streamChat(
            UUID conversationId,
            String message,
            String imageUrl,
            ModelId modelId,
            List<String> userMemories,
            boolean continuationExpected,
            Consumer<StreamEvent> eventConsumer
    );

    void recoverStreamChat(
            UUID conversationId,
            String message,
            String imageUrl,
            ModelId modelId,
            List<String> userMemories,
            List<RecoveryMessage> recoveryHistory,
            Consumer<StreamEvent> eventConsumer
    );

    default void streamChat(
            UUID conversationId,
            String message,
            String imageUrl,
            Consumer<StreamEvent> eventConsumer
    ) {
        streamChat(
                conversationId,
                message,
                imageUrl,
                ModelId.STEP_FLASH_3_7,
                eventConsumer
        );
    }

    List<ModelDescriptor> listModels();

    ForumDraftResult generateForumDraft(
            UUID conversationId,
            List<DraftMessage> messages,
            ModelId modelId
    );

    List<ExtractedMemoryCandidate> extractMemories(
            String currentUserMessage,
            List<MemoryContextMessage> context,
            ModelId modelId
    );

    boolean isHealthy();

    void deleteConversationState(UUID conversationId);

    GeneratedImagePayload downloadGeneratedImage(UUID generationId);

    record ChatResult(
            UUID conversationId,
            String answer,
            List<GeneratedImageReference> generatedImages
    ) {
        public ChatResult(UUID conversationId, String answer) {
            this(conversationId, answer, List.of());
        }
    }

    record StreamEvent(
            String type,
            String stage,
            String message,
            String content,
            UUID generationId,
            String imageModel,
            String prompt
    ) {
        public StreamEvent(
                String type,
                String stage,
                String message,
                String content
        ) {
            this(type, stage, message, content, null, null, null);
        }
    }

    record GeneratedImageReference(
            UUID generationId,
            String imageModel,
            String prompt
    ) {
    }

    record GeneratedImagePayload(byte[] bytes, String contentType) {
    }

    record RecoveryMessage(
            @com.fasterxml.jackson.annotation.JsonProperty("message_id")
            long messageId,
            String role,
            String content
    ) {
    }

    record ModelDescriptor(
            ModelId id,
            String displayName,
            boolean supportsText,
            boolean supportsTools,
            boolean supportsStreaming,
            boolean supportsImages,
            boolean available
    ) {
    }

    record DraftMessage(String role, String content) {
    }

    record ForumDraftResult(
            String title,
            String content,
            String dishName
    ) {
    }

    enum MemoryAction {
        UPSERT,
        DELETE
    }

    record MemoryContextMessage(String role, String content) {
    }

    record ExtractedMemoryCandidate(
            MemoryAction action,
            @com.fasterxml.jackson.annotation.JsonProperty("memory_type")
            MemoryType memoryType,
            String key,
            String value,
            double confidence,
            @com.fasterxml.jackson.annotation.JsonProperty("source_text")
            String sourceText
    ) {
    }
}
