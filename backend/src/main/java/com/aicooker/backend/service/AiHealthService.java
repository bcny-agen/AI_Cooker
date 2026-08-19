package com.aicooker.backend.service;

import com.aicooker.backend.client.AiCookerClient;
import com.aicooker.backend.exception.AiServiceException;
import org.springframework.stereotype.Service;

@Service
public class AiHealthService {

    private final AiCookerClient aiCookerClient;

    public AiHealthService(AiCookerClient aiCookerClient) {
        this.aiCookerClient = aiCookerClient;
    }

    public boolean isAiServiceAvailable() {
        try {
            return aiCookerClient.isHealthy();
        } catch (AiServiceException exception) {
            return false;
        }
    }
}
