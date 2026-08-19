package com.aicooker.backend.service;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.List;
import java.util.UUID;

import com.aicooker.backend.client.AiCookerClient;
import com.aicooker.backend.entity.MemoryType;
import com.aicooker.backend.entity.ModelId;
import com.aicooker.backend.repository.MessageRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class MemoryExtractionServiceTest {

    @Mock
    private AiCookerClient aiCookerClient;
    @Mock
    private MessageRepository messageRepository;
    @Mock
    private UserMemoryService userMemoryService;
    private MemoryExtractionService service;

    @BeforeEach
    void setUp() {
        service = new MemoryExtractionService(
                aiCookerClient,
                messageRepository,
                userMemoryService
        );
    }

    @Test
    void groundedStablePreferenceIsAppliedToCorrectUser() {
        UUID userId = UUID.randomUUID();
        UUID conversationId = UUID.randomUUID();
        when(messageRepository
                .findTop8ByConversation_IdOrderByCreatedAtDescIdDesc(conversationId))
                .thenReturn(new java.util.ArrayList<>());
        var candidate = candidate("I prefer less oil", "oil", "low");
        when(aiCookerClient.extractMemories(
                eq("I prefer less oil."), any(), eq(ModelId.STEP_FLASH_3_7)
        )).thenReturn(List.of(candidate));

        service.extractSafely(
                userId,
                conversationId,
                "I prefer less oil.",
                ModelId.STEP_FLASH_3_7
        );

        verify(userMemoryService).applyExtractedMemories(
                userId,
                conversationId,
                List.of(candidate)
        );
    }

    @Test
    void assistantOnlyClaimCannotBecomeUserMemory() {
        UUID userId = UUID.randomUUID();
        UUID conversationId = UUID.randomUUID();
        when(messageRepository
                .findTop8ByConversation_IdOrderByCreatedAtDescIdDesc(conversationId))
                .thenReturn(new java.util.ArrayList<>());
        when(aiCookerClient.extractMemories(any(), any(), any())).thenReturn(List.of(
                candidate("You prefer less oil", "oil", "low")
        ));

        service.extractSafely(
                userId,
                conversationId,
                "Thanks for the recipe.",
                ModelId.STEP_FLASH_3_7
        );

        @SuppressWarnings("unchecked")
        ArgumentCaptor<List<AiCookerClient.ExtractedMemoryCandidate>> captor =
                ArgumentCaptor.forClass(List.class);
        verify(userMemoryService).applyExtractedMemories(
                eq(userId), eq(conversationId), captor.capture()
        );
        org.assertj.core.api.Assertions.assertThat(captor.getValue()).isEmpty();
    }

    @Test
    void temporaryFactAndNoCandidateDoNotForceMemory() {
        UUID conversationId = UUID.randomUUID();
        when(messageRepository
                .findTop8ByConversation_IdOrderByCreatedAtDescIdDesc(conversationId))
                .thenReturn(new java.util.ArrayList<>());
        when(aiCookerClient.extractMemories(any(), any(), any()))
                .thenReturn(List.of());

        service.extractSafely(
                UUID.randomUUID(),
                conversationId,
                "I have three eggs today.",
                ModelId.STEP_FLASH_3_7
        );

        verify(userMemoryService, never()).applyExtractedMemories(
                any(), any(), any()
        );
    }

    @Test
    void extractionFailureDoesNotEscapeSuccessfulChatPostProcessing() {
        UUID conversationId = UUID.randomUUID();
        when(messageRepository
                .findTop8ByConversation_IdOrderByCreatedAtDescIdDesc(conversationId))
                .thenReturn(new java.util.ArrayList<>());
        doThrow(new RuntimeException("model unavailable"))
                .when(aiCookerClient).extractMemories(any(), any(), any());

        service.extractSafely(
                UUID.randomUUID(),
                conversationId,
                "I prefer mild food.",
                ModelId.STEP_FLASH_3_7
        );

        verify(userMemoryService, never()).applyExtractedMemories(
                any(), any(), any()
        );
    }

    private static AiCookerClient.ExtractedMemoryCandidate candidate(
            String source,
            String key,
            String value
    ) {
        return new AiCookerClient.ExtractedMemoryCandidate(
                AiCookerClient.MemoryAction.UPSERT,
                MemoryType.COOKING_PREFERENCE,
                key,
                value,
                0.95,
                source
        );
    }
}
