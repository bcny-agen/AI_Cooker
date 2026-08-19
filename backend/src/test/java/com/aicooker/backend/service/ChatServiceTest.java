package com.aicooker.backend.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.net.ConnectException;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.time.Instant;

import com.aicooker.backend.client.AiCookerClient;
import com.aicooker.backend.dto.ChatRequest;
import com.aicooker.backend.dto.ChatStreamEvent;
import com.aicooker.backend.dto.GeneratedImageResponse;
import com.aicooker.backend.entity.ModelId;
import com.aicooker.backend.exception.AiServiceServerException;
import com.aicooker.backend.exception.AiServiceUnavailableException;
import com.aicooker.backend.exception.AiThreadRecoveryRequiredException;
import com.aicooker.backend.exception.ModelCapabilityException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class ChatServiceTest {

    private static final UUID USER_ID =
            UUID.fromString("0f0c2f0d-a51b-44f6-915b-ed9d3f583804");
    private static final UUID IMAGE_ID =
            UUID.fromString("eb7f8917-5655-49c8-bf63-1ba193b7f2e2");

    @Mock
    private AiCookerClient aiCookerClient;
    @Mock
    private ConversationPersistenceService conversationPersistenceService;
    @Mock
    private ImageService imageService;
    @Mock
    private ModelCatalogService modelCatalogService;
    @Mock
    private UserMemoryService userMemoryService;
    @Mock
    private MemoryExtractionService memoryExtractionService;
    @Mock
    private GeneratedImageService generatedImageService;
    @InjectMocks
    private ChatService chatService;

    @BeforeEach
    void modelDefaults() {
        lenient().when(userMemoryService.contextForAgent(any()))
                .thenReturn(List.of());
        lenient().when(conversationPersistenceService.resolveChatContext(
                any(), any(), any()
        ))
                .thenAnswer(invocation -> {
                    ModelId requested = invocation.getArgument(2);
                    return new ConversationPersistenceService.ChatContext(
                            requested == null
                                    ? ModelId.STEP_FLASH_3_7 : requested,
                            true
                    );
                });
        lenient().when(conversationPersistenceService.recordUserMessage(
                any(), any(), any(), any(), any()
        )).thenReturn(new ConversationPersistenceService.RecordedUserMessage(42L));
        when(modelCatalogService.requireAvailable(any())).thenAnswer(invocation -> {
            ModelId id = invocation.getArgument(0);
            return model(id, id == ModelId.STEP_FLASH_3_7);
        });
    }

    @Test
    void generatesIdAndPersistsVisibleMessagesInOrder() {
        when(aiCookerClient.chat(
                any(UUID.class),
                eq("I have eggs"),
                isNull(),
                eq(ModelId.STEP_FLASH_3_7),
                eq(List.of()),
                eq(true)
        )).thenAnswer(invocation -> new AiCookerClient.ChatResult(
                invocation.getArgument(0),
                "Cook an omelette"
        ));

        var response = chatService.chat(
                USER_ID,
                new ChatRequest(null, "I have eggs", null, null)
        );

        var ordered = inOrder(conversationPersistenceService, aiCookerClient);
        ordered.verify(conversationPersistenceService).recordUserMessage(
                USER_ID, response.conversationId(), "I have eggs", null,
                ModelId.STEP_FLASH_3_7
        );
        ordered.verify(aiCookerClient).chat(
            response.conversationId(), "I have eggs", null,
                ModelId.STEP_FLASH_3_7, List.of(), true
        );
        ordered.verify(conversationPersistenceService).recordAssistantMessage(
                USER_ID, response.conversationId(), "Cook an omelette"
        );
    }

    @Test
    void creatingConversationUsesSelectedDeepseekModel() {
        when(aiCookerClient.chat(
                any(), any(), isNull(), eq(ModelId.DEEPSEEK_V4_PRO), eq(List.of()),
                eq(true)
        ))
                .thenAnswer(invocation -> new AiCookerClient.ChatResult(
                        invocation.getArgument(0), "DeepSeek answer"
                ));

        chatService.chat(USER_ID, new ChatRequest(
                null, "I have tofu", null, ModelId.DEEPSEEK_V4_PRO
        ));

        verify(conversationPersistenceService).recordUserMessage(
                eq(USER_ID), any(), eq("I have tofu"), isNull(),
                eq(ModelId.DEEPSEEK_V4_PRO)
        );
        verify(aiCookerClient).chat(
                any(), eq("I have tofu"), isNull(),
                eq(ModelId.DEEPSEEK_V4_PRO), eq(List.of()), eq(true)
        );
    }

    @Test
    void continuingConversationUsesPersistedModel() {
        UUID conversationId = UUID.randomUUID();
        when(conversationPersistenceService.resolveChatContext(
                USER_ID, conversationId, null
        )).thenReturn(new ConversationPersistenceService.ChatContext(
                ModelId.DEEPSEEK_V4_PRO, true
        ));
        when(aiCookerClient.chat(
                conversationId, "continue", null,
                ModelId.DEEPSEEK_V4_PRO, List.of(), true
        )).thenReturn(new AiCookerClient.ChatResult(conversationId, "answer"));

        chatService.chat(USER_ID, new ChatRequest(
                conversationId, "continue", null, null
        ));

        verify(aiCookerClient).chat(
                conversationId, "continue", null,
                ModelId.DEEPSEEK_V4_PRO, List.of(), true
        );
        verify(aiCookerClient, never()).recoverChat(
                any(), any(), any(), any(), any(), any()
        );
    }

    @Test
    void sendsExistingUserMemoryToNewConversationAgentCall() {
        var memoryContext = List.of(
                "Dietary restriction — coriander: avoid",
                "Cooking preference — oil: low"
        );
        when(userMemoryService.contextForAgent(USER_ID)).thenReturn(memoryContext);
        when(aiCookerClient.chat(
                any(), eq("Recommend dinner"), isNull(),
                eq(ModelId.STEP_FLASH_3_7), eq(memoryContext), eq(true)
        )).thenAnswer(invocation -> new AiCookerClient.ChatResult(
                invocation.getArgument(0),
                "A low-oil coriander-free dinner"
        ));

        chatService.chat(
                USER_ID,
                new ChatRequest(null, "Recommend dinner", null, null)
        );

        verify(aiCookerClient).chat(
                any(), eq("Recommend dinner"), isNull(),
                eq(ModelId.STEP_FLASH_3_7), eq(memoryContext), eq(true)
        );
    }

    @Test
    void unsupportedImageStopsBeforePersistenceAndAiCall() {
        UUID conversationId = UUID.randomUUID();
        when(conversationPersistenceService.resolveChatContext(any(), any(), any()))
                .thenReturn(new ConversationPersistenceService.ChatContext(
                        ModelId.DEEPSEEK_V4_PRO, true
                ));

        assertThatThrownBy(() -> chatService.chat(USER_ID, new ChatRequest(
                conversationId, "inspect", IMAGE_ID, ModelId.DEEPSEEK_V4_PRO
        ))).isInstanceOf(ModelCapabilityException.class);

        verify(imageService, never()).resolveForChat(any(), any());
        verify(conversationPersistenceService, never()).recordUserMessage(
                any(), any(), any(), any(), any()
        );
        verify(aiCookerClient, never()).chat(
                any(), any(), any(), any(), any()
        );
    }

    @Test
    void keepsUserMessageButDoesNotCreateAssistantMessageWhenPythonFails() {
        UUID conversationId = UUID.randomUUID();
        when(aiCookerClient.chat(
                conversationId, "hello", null,
                ModelId.STEP_FLASH_3_7, List.of(), true
        )).thenThrow(new AiServiceUnavailableException(new ConnectException("refused")));

        assertThatThrownBy(() -> chatService.chat(USER_ID,
                new ChatRequest(conversationId, "hello", null, null)
        )).isInstanceOf(AiServiceUnavailableException.class);

        verify(conversationPersistenceService).recordUserMessage(
                USER_ID, conversationId, "hello", null, ModelId.STEP_FLASH_3_7
        );
        verify(conversationPersistenceService, never())
                .recordAssistantMessage(any(), any(), any());
    }

    @Test
    void doesNotPersistAssistantMessageForMismatchedPythonResponse() {
        UUID conversationId = UUID.randomUUID();
        when(aiCookerClient.chat(
                conversationId, "hello", null,
                ModelId.STEP_FLASH_3_7, List.of(), true
        )).thenReturn(new AiCookerClient.ChatResult(UUID.randomUUID(), "answer"));

        assertThatThrownBy(() -> chatService.chat(USER_ID,
                new ChatRequest(conversationId, "hello", null, null)
        )).isInstanceOf(AiServiceServerException.class);
        verify(conversationPersistenceService, never())
                .recordAssistantMessage(any(), any(), any());
    }

    @Test
    void streamingAccumulatesTextAndPersistsAssistantOnlyAfterDone() {
        UUID conversationId = UUID.randomUUID();
        ChatService.StreamSession session = chatService.beginStream(
                USER_ID,
                new ChatRequest(conversationId, "I have eggs", null, null)
        );
        doAnswer(invocation -> {
            @SuppressWarnings("unchecked")
            var consumer = (java.util.function.Consumer<AiCookerClient.StreamEvent>)
                    invocation.getArgument(6);
            consumer.accept(new AiCookerClient.StreamEvent(
                    "status", "thinking", "ignored", null
            ));
            consumer.accept(new AiCookerClient.StreamEvent(
                    "token", null, null, "Cook "
            ));
            verify(conversationPersistenceService, never())
                    .recordAssistantMessage(any(), any(), any());
            consumer.accept(new AiCookerClient.StreamEvent(
                    "token", null, null, "eggs."
            ));
            verify(memoryExtractionService, never()).extractSafely(
                    any(), any(), any(), any()
            );
            consumer.accept(new AiCookerClient.StreamEvent(
                    "done", null, null, null
            ));
            return null;
        }).when(aiCookerClient).streamChat(
                eq(conversationId), eq("I have eggs"), isNull(),
                eq(ModelId.STEP_FLASH_3_7), eq(List.of()), eq(true), any()
        );
        List<ChatStreamEvent> events = new ArrayList<>();

        chatService.stream(session, events::add);

        verify(conversationPersistenceService).recordAssistantMessage(
                USER_ID, conversationId, "Cook eggs."
        );
        verify(memoryExtractionService).extractSafely(
                USER_ID,
                conversationId,
                "I have eggs",
                ModelId.STEP_FLASH_3_7
        );
        assertThat(events).extracting(ChatStreamEvent::type)
                .containsExactly("status", "token", "token", "status", "done");
    }

    @Test
    void streamingImageEventPersistsAfterAssistantAndReturnsSignedPreview() {
        UUID conversationId = UUID.randomUUID();
        UUID generationId = UUID.randomUUID();
        UUID storedImageId = UUID.randomUUID();
        ChatService.StreamSession session = chatService.beginStream(
                USER_ID,
                new ChatRequest(
                        conversationId,
                        "Generate an image of the second dish",
                        null,
                        null
                )
        );
        when(conversationPersistenceService.recordAssistantMessage(
                USER_ID, conversationId, "Here is the dish."
        )).thenReturn(
                new ConversationPersistenceService.RecordedAssistantMessage(52L)
        );
        var reference = new AiCookerClient.GeneratedImageReference(
                generationId,
                "step-image-edit-2",
                "A grounded food photo"
        );
        var stored = new GeneratedImageResponse(
                storedImageId,
                "https://signed.example/generated",
                "step-image-edit-2",
                Instant.parse("2026-08-09T12:00:00Z")
        );
        when(generatedImageService.store(
                USER_ID, conversationId, 52L, reference
        )).thenReturn(stored);
        doAnswer(invocation -> {
            @SuppressWarnings("unchecked")
            var consumer = (java.util.function.Consumer<AiCookerClient.StreamEvent>)
                    invocation.getArgument(6);
            consumer.accept(new AiCookerClient.StreamEvent(
                    "status", "generating_image", null, null
            ));
            consumer.accept(new AiCookerClient.StreamEvent(
                    "token", null, null, "Here is the dish."
            ));
            consumer.accept(new AiCookerClient.StreamEvent(
                    "generated_image",
                    null,
                    null,
                    null,
                    generationId,
                    "step-image-edit-2",
                    "A grounded food photo"
            ));
            consumer.accept(new AiCookerClient.StreamEvent(
                    "done", null, null, null
            ));
            return null;
        }).when(aiCookerClient).streamChat(
                eq(conversationId),
                eq("Generate an image of the second dish"),
                isNull(),
                eq(ModelId.STEP_FLASH_3_7),
                eq(List.of()),
                eq(true),
                any()
        );
        List<ChatStreamEvent> events = new ArrayList<>();

        chatService.stream(session, events::add);

        verify(generatedImageService).store(
                USER_ID, conversationId, 52L, reference
        );
        assertThat(events).extracting(ChatStreamEvent::type).containsExactly(
                "status", "token", "generated_image", "status", "done"
        );
        assertThat(events.get(2).generatedImage().imageId())
                .isEqualTo(storedImageId);
    }

    @Test
    void imageStorageFailureDoesNotDiscardAssistantText() {
        UUID conversationId = UUID.randomUUID();
        UUID generationId = UUID.randomUUID();
        ChatService.StreamSession session = chatService.beginStream(
                USER_ID,
                new ChatRequest(conversationId, "Show the dish", null, null)
        );
        when(conversationPersistenceService.recordAssistantMessage(
                USER_ID, conversationId, "Text still works."
        )).thenReturn(
                new ConversationPersistenceService.RecordedAssistantMessage(53L)
        );
        when(generatedImageService.store(any(), any(), any(), any()))
                .thenThrow(new com.aicooker.backend.exception.ImageStorageException(
                        "OSS unavailable"
                ));
        doAnswer(invocation -> {
            @SuppressWarnings("unchecked")
            var consumer = (java.util.function.Consumer<AiCookerClient.StreamEvent>)
                    invocation.getArgument(6);
            consumer.accept(new AiCookerClient.StreamEvent(
                    "token", null, null, "Text still works."
            ));
            consumer.accept(new AiCookerClient.StreamEvent(
                    "generated_image", null, null, null,
                    generationId, "step-image-edit-2", "A food photo"
            ));
            consumer.accept(new AiCookerClient.StreamEvent(
                    "done", null, null, null
            ));
            return null;
        }).when(aiCookerClient).streamChat(
                eq(conversationId), eq("Show the dish"), isNull(),
                eq(ModelId.STEP_FLASH_3_7), eq(List.of()), eq(true), any()
        );
        List<ChatStreamEvent> events = new ArrayList<>();

        chatService.stream(session, events::add);

        verify(conversationPersistenceService).recordAssistantMessage(
                USER_ID, conversationId, "Text still works."
        );
        assertThat(events).extracting(ChatStreamEvent::type)
                .contains("token", "image_error", "done");
    }

    @Test
    void streamingFailureKeepsUserMessageWithoutFakeAssistant() {
        UUID conversationId = UUID.randomUUID();
        ChatService.StreamSession session = chatService.beginStream(
                USER_ID,
                new ChatRequest(conversationId, "I have eggs", null, null)
        );
        doAnswer(invocation -> {
            @SuppressWarnings("unchecked")
            var consumer = (java.util.function.Consumer<AiCookerClient.StreamEvent>)
                    invocation.getArgument(6);
            consumer.accept(new AiCookerClient.StreamEvent(
                    "token", null, null, "Incomplete"
            ));
            consumer.accept(new AiCookerClient.StreamEvent(
                    "error", null, "safe error", null
            ));
            return null;
        }).when(aiCookerClient).streamChat(
                eq(conversationId), eq("I have eggs"), isNull(),
                eq(ModelId.STEP_FLASH_3_7), eq(List.of()), eq(true), any()
        );
        List<ChatStreamEvent> events = new ArrayList<>();

        chatService.stream(session, events::add);

        verify(conversationPersistenceService, never())
                .recordAssistantMessage(any(), any(), any());
        assertThat(events).extracting(ChatStreamEvent::type)
                .containsExactly("token", "error");
    }

    @Test
    void forwardsRealContextSummarizationStatus() {
        UUID conversationId = UUID.randomUUID();
        ChatService.StreamSession session = chatService.beginStream(
                USER_ID,
                new ChatRequest(conversationId, "continue", null, null)
        );
        doAnswer(invocation -> {
            @SuppressWarnings("unchecked")
            var consumer = (java.util.function.Consumer<AiCookerClient.StreamEvent>)
                    invocation.getArgument(6);
            consumer.accept(new AiCookerClient.StreamEvent(
                    "status",
                    "summarizing_context",
                    "ignored internal wording",
                    null
            ));
            consumer.accept(new AiCookerClient.StreamEvent(
                    "token", null, null, "Answer"
            ));
            consumer.accept(new AiCookerClient.StreamEvent(
                    "done", null, null, null
            ));
            return null;
        }).when(aiCookerClient).streamChat(
                eq(conversationId), eq("continue"), isNull(),
                eq(ModelId.STEP_FLASH_3_7), eq(List.of()), eq(true), any()
        );
        List<ChatStreamEvent> events = new ArrayList<>();

        chatService.stream(session, events::add);

        assertThat(events).anySatisfy(event -> {
            assertThat(event.type()).isEqualTo("status");
            assertThat(event.stage()).isEqualTo("summarizing_context");
            assertThat(event.message()).isEqualTo(
                    "Compressing older conversation context..."
            );
        });
    }

    @Test
    void legacyThreadIsRecoveredOnceWithAuthorizedHistory() {
        UUID conversationId = UUID.randomUUID();
        when(aiCookerClient.chat(
                conversationId, "continue", null,
                ModelId.STEP_FLASH_3_7, List.of(), true
        )).thenThrow(new AiThreadRecoveryRequiredException(
                new IllegalStateException("missing_checkpoint")
        )).thenReturn(new AiCookerClient.ChatResult(
                conversationId,
                "next normal continuation"
        ));
        when(conversationPersistenceService.recoveryHistory(
                USER_ID, conversationId, 42L
        )).thenReturn(List.of(
                new ConversationPersistenceService.RecoveryHistoryMessage(
                        10L,
                        com.aicooker.backend.entity.MessageRole.USER,
                        "Earlier question"
                ),
                new ConversationPersistenceService.RecoveryHistoryMessage(
                        11L,
                        com.aicooker.backend.entity.MessageRole.ASSISTANT,
                        "Earlier answer"
                )
        ));
        when(aiCookerClient.recoverChat(
                eq(conversationId), eq("continue"), isNull(),
                eq(ModelId.STEP_FLASH_3_7), eq(List.of()), any()
        )).thenReturn(new AiCookerClient.ChatResult(conversationId, "continued"));

        var response = chatService.chat(
                USER_ID,
                new ChatRequest(conversationId, "continue", null, null)
        );

        assertThat(response.conversationId()).isEqualTo(conversationId);
        verify(aiCookerClient).recoverChat(
                conversationId,
                "continue",
                null,
                ModelId.STEP_FLASH_3_7,
                List.of(),
                List.of(
                        new AiCookerClient.RecoveryMessage(
                                10L, "USER", "Earlier question"
                        ),
                        new AiCookerClient.RecoveryMessage(
                                11L, "ASSISTANT", "Earlier answer"
                        )
                )
        );

        var nextResponse = chatService.chat(
                USER_ID,
                new ChatRequest(conversationId, "continue", null, null)
        );
        assertThat(nextResponse.answer()).isEqualTo("next normal continuation");
        verify(aiCookerClient).recoverChat(
                any(), any(), any(), any(), any(), any()
        );
    }

    private static AiCookerClient.ModelDescriptor model(
            ModelId id,
            boolean supportsImages
    ) {
        return new AiCookerClient.ModelDescriptor(
                id,
                id == ModelId.STEP_FLASH_3_7
                        ? "Step 3.7 Flash" : "DeepSeek V4 Pro",
                true,
                true,
                true,
                supportsImages,
                true
        );
    }
}
