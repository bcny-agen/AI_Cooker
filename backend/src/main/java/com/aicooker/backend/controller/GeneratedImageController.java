package com.aicooker.backend.controller;

import java.security.Principal;
import java.util.UUID;

import com.aicooker.backend.dto.GeneratedImageResponse;
import com.aicooker.backend.security.AuthenticatedUser;
import com.aicooker.backend.service.GeneratedImageService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/generated-images")
public class GeneratedImageController {

    private final GeneratedImageService generatedImageService;

    public GeneratedImageController(GeneratedImageService generatedImageService) {
        this.generatedImageService = generatedImageService;
    }

    @GetMapping("/{imageId}")
    public GeneratedImageResponse get(
            Principal principal,
            @PathVariable UUID imageId
    ) {
        return generatedImageService.get(
                AuthenticatedUser.id(principal),
                imageId
        );
    }
}
