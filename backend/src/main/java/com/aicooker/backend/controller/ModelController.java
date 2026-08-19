package com.aicooker.backend.controller;

import java.util.List;

import com.aicooker.backend.dto.ModelResponse;
import com.aicooker.backend.service.ModelCatalogService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/models")
public class ModelController {

    private final ModelCatalogService modelCatalogService;

    public ModelController(ModelCatalogService modelCatalogService) {
        this.modelCatalogService = modelCatalogService;
    }

    @GetMapping
    public List<ModelResponse> listModels() {
        return modelCatalogService.listModels();
    }
}
