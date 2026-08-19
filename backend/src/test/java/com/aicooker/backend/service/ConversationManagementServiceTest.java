package com.aicooker.backend.service;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.UUID;

import com.aicooker.backend.client.AiCookerClient;
import com.aicooker.backend.exception.AiServiceUnavailableException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class ConversationManagementServiceTest {

    private final UUID userId = UUID.randomUUID();
    private final UUID conversationId = UUID.randomUUID();
    private ConversationManagementPersistenceService persistenceService;
    private AiCookerClient aiCookerClient;
    private ConversationManagementService service;

    @BeforeEach
    void setUp() {
        persistenceService = org.mockito.Mockito.mock(
                ConversationManagementPersistenceService.class
        );
        aiCookerClient = org.mockito.Mockito.mock(AiCookerClient.class);
        service = new ConversationManagementService(
                persistenceService,
                aiCookerClient
        );
    }

    @Test
    void renameChangesOnlyBusinessMetadata() {
        service.rename(userId, conversationId, "New title");

        verify(persistenceService).rename(
                userId, conversationId, "New title"
        );
        verify(aiCookerClient, never()).deleteConversationState(
                conversationId
        );
    }

    @Test
    void deletionVerifiesOwnerThenDeletesPythonBeforeJava() {
        service.delete(userId, conversationId);

        var ordered = inOrder(persistenceService, aiCookerClient);
        ordered.verify(persistenceService).requireOwnership(
                userId, conversationId
        );
        ordered.verify(aiCookerClient).deleteConversationState(conversationId);
        ordered.verify(persistenceService).deleteBusinessConversation(
                userId, conversationId
        );
    }

    @Test
    void pythonCleanupFailureLeavesBusinessConversationIntact() {
        org.mockito.Mockito.doThrow(new AiServiceUnavailableException(
                new IllegalStateException("offline")
        )).when(aiCookerClient).deleteConversationState(conversationId);

        assertThatThrownBy(() -> service.delete(userId, conversationId))
                .isInstanceOf(AiServiceUnavailableException.class);

        verify(persistenceService, never()).deleteBusinessConversation(
                userId, conversationId
        );
    }

    @Test
    void javaFailureHappensAfterPythonCleanupSoRecoveryCanRebuildLater() {
        org.mockito.Mockito.doThrow(new IllegalStateException("database failed"))
                .when(persistenceService)
                .deleteBusinessConversation(userId, conversationId);

        assertThatThrownBy(() -> service.delete(userId, conversationId))
                .isInstanceOf(IllegalStateException.class);

        verify(aiCookerClient).deleteConversationState(conversationId);
    }
}
