package com.aicooker.backend.service;

import java.util.UUID;
import java.util.function.Consumer;

import com.aicooker.backend.client.AiCookerClient;
import com.aicooker.backend.dto.ChatRequest;
import com.aicooker.backend.dto.ChatResponse;
import com.aicooker.backend.dto.ChatStreamEvent;
import com.aicooker.backend.exception.AiServiceServerException;
import com.aicooker.backend.exception.AiThreadRecoveryRequiredException;
import com.aicooker.backend.entity.ModelId;
import com.aicooker.backend.exception.ModelCapabilityException;
import org.springframework.stereotype.Service;
import org.springframework.beans.factory.annotation.Autowired;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

@Service
public class ChatService {

    private static final Logger LOGGER = LoggerFactory.getLogger(ChatService.class);

    private final AiCookerClient aiCookerClient;
    private final ConversationPersistenceService conversationPersistenceService;
    private final ImageService imageService;
    private final ModelCatalogService modelCatalogService;
    private final UserMemoryService userMemoryService;
    private final MemoryExtractionService memoryExtractionService;
    private final GeneratedImageService generatedImageService;

    @Autowired
    public ChatService(
            AiCookerClient aiCookerClient,
            ConversationPersistenceService conversationPersistenceService,
            ImageService imageService,
            ModelCatalogService modelCatalogService,
            UserMemoryService userMemoryService,
            MemoryExtractionService memoryExtractionService,
            GeneratedImageService generatedImageService
    ) {
        this.aiCookerClient = aiCookerClient;
        this.conversationPersistenceService = conversationPersistenceService;
        this.imageService = imageService;
        this.modelCatalogService = modelCatalogService;
        this.userMemoryService = userMemoryService;
        this.memoryExtractionService = memoryExtractionService;
        this.generatedImageService = generatedImageService;
    }

    public ChatResponse chat(UUID userId, ChatRequest request) {
        UUID conversationId = request.conversationId() != null
                ? request.conversationId()
                : UUID.randomUUID();
        var chatContext = resolveChatContext(userId, conversationId, request);
        ModelId modelId = chatContext.modelId();
        String imageUrl = request.imageId() == null
                ? null
                : imageService.resolveForChat(userId, request.imageId()).url();
        var userMemories = userMemoryService.contextForAgent(userId);

        var recordedUserMessage = conversationPersistenceService.recordUserMessage(
                userId,
                conversationId,
                request.message(),
                request.imageId(),
                modelId
        );

        AiCookerClient.ChatResult result;
        try {
            result = aiCookerClient.chat(
                    conversationId,
                    request.message(),
                    imageUrl,
                    modelId,
                    userMemories,
                    chatContext.existingConversation()
            );
        } catch (AiThreadRecoveryRequiredException exception) {
            result = aiCookerClient.recoverChat(
                    conversationId,
                    request.message(),
                    imageUrl,
                    modelId,
                    userMemories,
                    recoveryHistory(
                            userId,
                            conversationId,
                            recordedUserMessage.messageId()
                    )
            );
        }

        if (result == null
                || result.answer() == null
                || !conversationId.equals(result.conversationId())) {
            throw new AiServiceServerException(
                    "The Python AI service returned a mismatched conversation ID."
            );
        }

        var assistantMessage = conversationPersistenceService.recordAssistantMessage(
                userId,
                conversationId,
                result.answer()
        );
        var generatedImages = storeGeneratedImagesSafely(
                userId,
                conversationId,
                assistantMessage,
                result.generatedImages()
        );
        memoryExtractionService.extractSafely(
                userId,
                conversationId,
                request.message(),
                modelId
        );

        return new ChatResponse(
                result.conversationId(),
                result.answer(),
                generatedImages
        );
    }

    public StreamSession beginStream(UUID userId, ChatRequest request) {
        UUID conversationId = request.conversationId() != null
                ? request.conversationId()
                : UUID.randomUUID();
        var chatContext = resolveChatContext(userId, conversationId, request);
        ModelId modelId = chatContext.modelId();
        String imageUrl = request.imageId() == null
                ? null
                : imageService.resolveForChat(userId, request.imageId()).url();
        var userMemories = userMemoryService.contextForAgent(userId);

        var recordedUserMessage = conversationPersistenceService.recordUserMessage(
                userId,
                conversationId,
                request.message(),
                request.imageId(),
                modelId
        );

        return new StreamSession(
                userId,
                conversationId,
                request.message(),
                imageUrl,
                modelId,
                userMemories,
                chatContext.existingConversation(),
                recordedUserMessage.messageId()
        );
    }

    public void stream(
            StreamSession session,
            Consumer<ChatStreamEvent> eventConsumer
    ) {
        var state = new StreamState();

        try {
            aiCookerClient.streamChat(
                    session.conversationId(),
                    session.message(),
                    session.imageUrl(),
                    session.modelId(),
                    session.userMemories(),
                    session.continuationExpected(),
                    event -> handleAgentEvent(session, event, eventConsumer, state)
            );
        } catch (AiThreadRecoveryRequiredException exception) {
            if (!state.answer.isEmpty() || state.terminal) {
                throw new AiServiceServerException(
                        "Thread recovery was requested after streaming began."
                );
            }
            aiCookerClient.recoverStreamChat(
                    session.conversationId(),
                    session.message(),
                    session.imageUrl(),
                    session.modelId(),
                    session.userMemories(),
                    recoveryHistory(
                            session.userId(),
                            session.conversationId(),
                            session.currentUserMessageId()
                    ),
                    event -> handleAgentEvent(session, event, eventConsumer, state)
            );
        }

        if (!state.terminal) {
            throw new AiServiceServerException(
                    "The Python AI stream ended without completion."
            );
        }
        if (state.completed) {
            memoryExtractionService.extractSafely(
                    session.userId(),
                    session.conversationId(),
                    session.message(),
                    session.modelId()
            );
        }
    }

    private ConversationPersistenceService.ChatContext resolveChatContext(
            UUID userId,
            UUID conversationId,
            ChatRequest request
    ) {
        var chatContext = conversationPersistenceService.resolveChatContext(
                userId,
                conversationId,
                request.modelId()
        );
        ModelId modelId = chatContext.modelId();
        AiCookerClient.ModelDescriptor model = modelCatalogService
                .requireAvailable(modelId);
        if (request.imageId() != null && !model.supportsImages()) {
            throw new ModelCapabilityException(
                    "The selected model does not support image input."
            );
        }
        return chatContext;
    }

    private java.util.List<AiCookerClient.RecoveryMessage> recoveryHistory(
            UUID userId,
            UUID conversationId,
            Long beforeMessageId
    ) {
        return conversationPersistenceService
                .recoveryHistory(userId, conversationId, beforeMessageId)
                .stream()
                .map(message -> new AiCookerClient.RecoveryMessage(
                        message.messageId(),
                        message.role().name(),
                        message.content()
                ))
                .toList();
    }

    private void handleAgentEvent(
            StreamSession session,
            AiCookerClient.StreamEvent event,
            Consumer<ChatStreamEvent> eventConsumer,
            StreamState state
    ) {
        if (state.terminal) {
            return;
        }

        switch (event.type()) {
            case "status" -> {
                ChatStreamEvent status = publicStatus(
                        session.conversationId(),
                        event.stage()
                );
                if (status != null && !"completed".equals(event.stage())) {
                    eventConsumer.accept(status);
                }
            }
            case "token" -> {
                if (event.content() == null || event.content().isEmpty()) {
                    return;
                }
                state.answer.append(event.content());
                eventConsumer.accept(ChatStreamEvent.token(
                        session.conversationId(),
                        event.content()
                ));
            }
            case "generated_image" -> {
                if (event.generationId() == null
                        || event.imageModel() == null
                        || event.prompt() == null) {
                    throw new AiServiceServerException(
                            "The Python AI stream returned incomplete image metadata."
                    );
                }
                if (state.generatedImage == null) {
                    state.generatedImage = new AiCookerClient.GeneratedImageReference(
                            event.generationId(),
                            event.imageModel(),
                            event.prompt()
                    );
                }
            }
            case "image_error" -> {
                if (!state.imageErrorEmitted) {
                    eventConsumer.accept(ChatStreamEvent.imageError(
                            session.conversationId()
                    ));
                    state.imageErrorEmitted = true;
                }
            }
            case "done" -> {
                if (state.answer.isEmpty()) {
                    throw new AiServiceServerException(
                            "The Python AI stream returned an empty answer."
                    );
                }
                var assistantMessage = conversationPersistenceService
                        .recordAssistantMessage(
                        session.userId(),
                        session.conversationId(),
                        state.answer.toString()
                );
                if (state.generatedImage != null && generatedImageService != null) {
                    try {
                        var image = generatedImageService.store(
                                session.userId(),
                                session.conversationId(),
                                assistantMessage.messageId(),
                                state.generatedImage
                        );
                        eventConsumer.accept(ChatStreamEvent.generatedImage(
                                session.conversationId(),
                                image
                        ));
                    } catch (RuntimeException exception) {
                        LOGGER.error(
                                "generated_image_persistence_failed conversationId={} "
                                        + "exception={}",
                                session.conversationId(),
                                exception.getClass().getSimpleName()
                        );
                        if (!state.imageErrorEmitted) {
                            eventConsumer.accept(ChatStreamEvent.imageError(
                                    session.conversationId()
                            ));
                            state.imageErrorEmitted = true;
                        }
                    }
                }
                eventConsumer.accept(ChatStreamEvent.status(
                        session.conversationId(),
                        "completed",
                        "Recommendation complete."
                ));
                eventConsumer.accept(ChatStreamEvent.done(session.conversationId()));
                state.terminal = true;
                state.completed = true;
            }
            case "error" -> {
                eventConsumer.accept(ChatStreamEvent.error(session.conversationId()));
                state.terminal = true;
            }
            default -> throw new AiServiceServerException(
                    "The Python AI stream returned an unsupported event."
            );
        }
    }

    private static ChatStreamEvent publicStatus(
            UUID conversationId,
            String stage
    ) {
        if (stage == null) {
            return null;
        }
        return switch (stage) {
            case "thinking" -> ChatStreamEvent.status(
                    conversationId,
                    stage,
                    "Thinking about your ingredients..."
            );
            case "analyzing_image" -> ChatStreamEvent.status(
                    conversationId,
                    stage,
                    "Analyzing the ingredient image..."
            );
            case "summarizing_context" -> ChatStreamEvent.status(
                    conversationId,
                    stage,
                    "Compressing older conversation context..."
            );
            case "searching_recipes" -> ChatStreamEvent.status(
                    conversationId,
                    stage,
                    "Searching for suitable recipes..."
            );
            case "generating_answer" -> ChatStreamEvent.status(
                    conversationId,
                    stage,
                    "Generating your recommendation..."
            );
            case "generating_image" -> ChatStreamEvent.status(
                    conversationId,
                    stage,
                    "Generating dish image..."
            );
            case "completed" -> ChatStreamEvent.status(
                    conversationId,
                    stage,
                    "Recommendation complete."
            );
            default -> null;
        };
    }

    public record StreamSession(
            UUID userId,
            UUID conversationId,
            String message,
            String imageUrl,
            ModelId modelId,
            java.util.List<String> userMemories,
            boolean continuationExpected,
            Long currentUserMessageId
    ) {
        public StreamSession(
                UUID userId,
                UUID conversationId,
                String message,
                String imageUrl
        ) {
            this(
                    userId,
                    conversationId,
                    message,
                    imageUrl,
                    ModelId.STEP_FLASH_3_7,
                    java.util.List.of(),
                    false,
                    -1L
            );
        }
    }

    private static final class StreamState {
        private final StringBuilder answer = new StringBuilder();
        private boolean terminal;
        private boolean completed;
        private boolean imageErrorEmitted;
        private AiCookerClient.GeneratedImageReference generatedImage;
    }

    private java.util.List<com.aicooker.backend.dto.GeneratedImageResponse>
    storeGeneratedImagesSafely(
            UUID userId,
            UUID conversationId,
            ConversationPersistenceService.RecordedAssistantMessage assistantMessage,
            java.util.List<AiCookerClient.GeneratedImageReference> references
    ) {
        if (generatedImageService == null
                || assistantMessage == null
                || references == null
                || references.isEmpty()) {
            return java.util.List.of();
        }
        try {
            return java.util.List.of(generatedImageService.store(
                    userId,
                    conversationId,
                    assistantMessage.messageId(),
                    references.getFirst()
            ));
        } catch (RuntimeException exception) {
            LOGGER.error(
                    "generated_image_persistence_failed conversationId={} exception={}",
                    conversationId,
                    exception.getClass().getSimpleName()
            );
            return java.util.List.of();
        }
    }
}
