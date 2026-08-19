package com.aicooker.backend.service;

import java.util.List;

import com.aicooker.backend.client.AiCookerClient;
import com.aicooker.backend.dto.ModelResponse;
import com.aicooker.backend.entity.ModelId;
import com.aicooker.backend.exception.ModelUnavailableException;
import org.springframework.stereotype.Service;

@Service
public class ModelCatalogService {

    private final AiCookerClient aiCookerClient;

    public ModelCatalogService(AiCookerClient aiCookerClient) {
        this.aiCookerClient = aiCookerClient;
    }

    public List<ModelResponse> listModels() {
        return aiCookerClient.listModels().stream()
                .map(ModelCatalogService::toResponse)
                .toList();
    }

    public AiCookerClient.ModelDescriptor requireAvailable(ModelId modelId) {
        return aiCookerClient.listModels().stream()
                .filter(item -> item.id() == modelId && item.available())
                .findFirst()
                .orElseThrow(() -> new ModelUnavailableException(modelId));
    }

    private static ModelResponse toResponse(
            AiCookerClient.ModelDescriptor descriptor
    ) {
        return new ModelResponse(
                descriptor.id(),
                descriptor.displayName(),
                descriptor.supportsText(),
                descriptor.supportsTools(),
                descriptor.supportsStreaming(),
                descriptor.supportsImages(),
                descriptor.available()
        );
    }
}
