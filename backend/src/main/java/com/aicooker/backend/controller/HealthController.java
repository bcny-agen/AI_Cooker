package com.aicooker.backend.controller;

import com.aicooker.backend.dto.HealthResponse;
import com.aicooker.backend.service.AiHealthService;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/health")
public class HealthController {

    private final AiHealthService aiHealthService;

    public HealthController(AiHealthService aiHealthService) {
        this.aiHealthService = aiHealthService;
    }

    @GetMapping
    public HealthResponse applicationHealth() {
        return new HealthResponse("UP");
    }

    @GetMapping("/ai")
    public ResponseEntity<HealthResponse> aiDependencyHealth() {
        boolean available = aiHealthService.isAiServiceAvailable();
        HttpStatus status = available ? HttpStatus.OK : HttpStatus.SERVICE_UNAVAILABLE;
        String bodyStatus = available ? "UP" : "DOWN";
        return ResponseEntity.status(status).body(new HealthResponse(bodyStatus));
    }
}
