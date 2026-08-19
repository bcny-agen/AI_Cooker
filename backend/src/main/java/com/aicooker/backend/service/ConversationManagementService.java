package com.aicooker.backend.service;

import java.util.UUID;

import com.aicooker.backend.client.AiCookerClient;
import com.aicooker.backend.dto.ConversationResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class ConversationManagementService {

    private static final Logger LOGGER = LoggerFactory.getLogger(
            ConversationManagementService.class
    );

    private final ConversationManagementPersistenceService persistenceService;
    private final AiCookerClient aiCookerClient;

    public ConversationManagementService(
            ConversationManagementPersistenceService persistenceService,
            AiCookerClient aiCookerClient
    ) {
        this.persistenceService = persistenceService;
        this.aiCookerClient = aiCookerClient;
    }

    public ConversationResponse rename(
            UUID userId,
            UUID conversationId,
            String title
    ) {
        return persistenceService.rename(userId, conversationId, title);
    }

    public void delete(UUID userId, UUID conversationId) {
        LOGGER.info(
                "conversation_delete operation=OWNERSHIP_CHECK_STARTED "
                        + "conversationId={}",
                conversationId
        );
        persistenceService.requireOwnership(userId, conversationId);
        LOGGER.info(
                "conversation_delete operation=OWNERSHIP_CHECK_SUCCEEDED "
                        + "conversationId={}",
                conversationId
        );
        LOGGER.info(
                "conversation_delete operation=PYTHON_CLEANUP_STARTED "
                        + "conversationId={}",
                conversationId
        );
        aiCookerClient.deleteConversationState(conversationId);
        LOGGER.info(
                "conversation_delete operation=PYTHON_CLEANUP_SUCCEEDED "
                        + "conversationId={}",
                conversationId
        );
        persistenceService.deleteBusinessConversation(userId, conversationId);
        LOGGER.info(
                "conversation_delete operation=BUSINESS_DELETE_SUCCEEDED "
                        + "conversationId={}",
                conversationId
        );
    }
}
