package com.aicooker.backend.controller;

import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.setup.MockMvcBuilders.standaloneSetup;

import com.aicooker.backend.service.AiHealthService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;

class HealthControllerTest {

    private AiHealthService aiHealthService;
    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        aiHealthService = org.mockito.Mockito.mock(AiHealthService.class);
        mockMvc = standaloneSetup(new HealthController(aiHealthService)).build();
    }

    @Test
    void applicationHealthDoesNotDependOnPython() throws Exception {
        mockMvc.perform(get("/api/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"));

        verify(aiHealthService, never()).isAiServiceAvailable();
    }

    @Test
    void aiHealthIsUpWhenPythonIsReachable() throws Exception {
        when(aiHealthService.isAiServiceAvailable()).thenReturn(true);

        mockMvc.perform(get("/api/health/ai"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"));
    }

    @Test
    void aiHealthIsDownWhenPythonIsUnavailable() throws Exception {
        when(aiHealthService.isAiServiceAvailable()).thenReturn(false);

        mockMvc.perform(get("/api/health/ai"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.status").value("DOWN"));
    }
}
