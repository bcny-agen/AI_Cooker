package com.aicooker.backend.service;

import java.util.UUID;

import com.aicooker.backend.dto.ConversationResponse;
import com.aicooker.backend.entity.ModelId;
import org.springframework.stereotype.Service;

@Service
public class ConversationModelService {

    private final ModelCatalogService modelCatalogService;
    private final ConversationPersistenceService persistenceService;
    private final ConversationQueryService queryService;

    public ConversationModelService(
            ModelCatalogService modelCatalogService,
            ConversationPersistenceService persistenceService,
            ConversationQueryService queryService
    ) {
        this.modelCatalogService = modelCatalogService;
        this.persistenceService = persistenceService;
        this.queryService = queryService;
    }

    public ConversationResponse changeModel(
            UUID userId,
            UUID conversationId,
            ModelId modelId
    ) {
        modelCatalogService.requireAvailable(modelId);
        persistenceService.changeModel(userId, conversationId, modelId);
        return queryService.getConversation(userId, conversationId);
    }
}
