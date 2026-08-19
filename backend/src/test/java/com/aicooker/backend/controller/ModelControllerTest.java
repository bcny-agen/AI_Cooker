package com.aicooker.backend.controller;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.setup.MockMvcBuilders.standaloneSetup;

import java.util.List;

import com.aicooker.backend.dto.ModelResponse;
import com.aicooker.backend.entity.ModelId;
import com.aicooker.backend.service.ModelCatalogService;
import org.junit.jupiter.api.Test;

class ModelControllerTest {

    @Test
    void exposesModelCapabilities() throws Exception {
        ModelCatalogService service = org.mockito.Mockito.mock(
                ModelCatalogService.class
        );
        when(service.listModels()).thenReturn(List.of(
                new ModelResponse(
                        ModelId.STEP_FLASH_3_7,
                        "Step 3.7 Flash",
                        true,
                        true,
                        true,
                        true,
                        true
                ),
                new ModelResponse(
                        ModelId.DEEPSEEK_V4_PRO,
                        "DeepSeek V4 Pro",
                        true,
                        true,
                        true,
                        false,
                        false
                )
        ));

        standaloneSetup(new ModelController(service)).build()
                .perform(get("/api/models"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].id").value("STEP_FLASH_3_7"))
                .andExpect(jsonPath("$[1].supportsImages").value(false))
                .andExpect(jsonPath("$[1].available").value(false));
    }
}
