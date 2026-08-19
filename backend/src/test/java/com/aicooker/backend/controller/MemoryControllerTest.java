package com.aicooker.backend.controller;

import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.setup.MockMvcBuilders.standaloneSetup;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import com.aicooker.backend.dto.MemoryResponse;
import com.aicooker.backend.dto.UpdateMemoryRequest;
import com.aicooker.backend.entity.MemoryType;
import com.aicooker.backend.exception.GlobalExceptionHandler;
import com.aicooker.backend.exception.MemoryNotFoundException;
import com.aicooker.backend.service.UserMemoryService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.test.web.servlet.MockMvc;

class MemoryControllerTest {

    private static final UUID USER_ID = UUID.randomUUID();
    private static final UUID MEMORY_ID = UUID.randomUUID();

    private UserMemoryService memoryService;
    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        memoryService = org.mockito.Mockito.mock(UserMemoryService.class);
        mockMvc = standaloneSetup(new MemoryController(memoryService))
                .setControllerAdvice(new GlobalExceptionHandler())
                .build();
    }

    @Test
    void listsOnlyAuthenticatedUsersMemories() throws Exception {
        when(memoryService.list(USER_ID)).thenReturn(List.of(memory()));

        mockMvc.perform(get("/api/memories").principal(principal()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].id").value(MEMORY_ID.toString()))
                .andExpect(jsonPath("$[0].memoryType")
                        .value("DIETARY_RESTRICTION"))
                .andExpect(jsonPath("$[0].confidence").doesNotExist())
                .andExpect(jsonPath("$[0].sourceConversationId").doesNotExist());
    }

    @Test
    void editsAndDeletesOwnedMemory() throws Exception {
        var request = new UpdateMemoryRequest(
                MemoryType.FOOD_PREFERENCE,
                "coriander",
                "dislike"
        );
        when(memoryService.update(USER_ID, MEMORY_ID, request))
                .thenReturn(new MemoryResponse(
                        MEMORY_ID,
                        MemoryType.FOOD_PREFERENCE,
                        "coriander",
                        "dislike",
                        Instant.parse("2026-01-01T00:00:00Z"),
                        Instant.parse("2026-01-02T00:00:00Z")
                ));

        mockMvc.perform(patch("/api/memories/{id}", MEMORY_ID)
                        .principal(principal())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "memoryType":"FOOD_PREFERENCE",
                                  "key":"coriander",
                                  "value":"dislike"
                                }
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.value").value("dislike"));

        mockMvc.perform(delete("/api/memories/{id}", MEMORY_ID)
                        .principal(principal()))
                .andExpect(status().isNoContent());
        verify(memoryService).delete(USER_ID, MEMORY_ID);
    }

    @Test
    void anotherUsersMemoryLooksNotFound() throws Exception {
        when(memoryService.list(USER_ID)).thenReturn(List.of());
        org.mockito.Mockito.doThrow(new MemoryNotFoundException(MEMORY_ID))
                .when(memoryService).delete(USER_ID, MEMORY_ID);

        mockMvc.perform(delete("/api/memories/{id}", MEMORY_ID)
                        .principal(principal()))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("MEMORY_NOT_FOUND"));
    }

    private static MemoryResponse memory() {
        Instant now = Instant.parse("2026-01-01T00:00:00Z");
        return new MemoryResponse(
                MEMORY_ID,
                MemoryType.DIETARY_RESTRICTION,
                "coriander",
                "avoid",
                now,
                now
        );
    }

    private static UsernamePasswordAuthenticationToken principal() {
        return new UsernamePasswordAuthenticationToken(
                USER_ID.toString(),
                "not-used"
        );
    }
}
