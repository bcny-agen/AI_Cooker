package com.aicooker.backend.controller;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.mockito.Mockito.never;
import static org.mockito.ArgumentMatchers.any;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.setup.MockMvcBuilders.standaloneSetup;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import com.aicooker.backend.dto.ConversationResponse;
import com.aicooker.backend.dto.MessageResponse;
import com.aicooker.backend.dto.PageResponse;
import com.aicooker.backend.entity.MessageRole;
import com.aicooker.backend.entity.ModelId;
import com.aicooker.backend.exception.ConversationNotFoundException;
import com.aicooker.backend.exception.GlobalExceptionHandler;
import com.aicooker.backend.service.ConversationQueryService;
import com.aicooker.backend.service.ConversationModelService;
import com.aicooker.backend.service.ConversationManagementService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;

class ConversationControllerTest {

    private static final UUID USER_ID =
            UUID.fromString("0f0c2f0d-a51b-44f6-915b-ed9d3f583804");
    private static final UUID CONVERSATION_ID =
            UUID.fromString("9b677223-0733-4d89-b13a-33f2a08ea610");
    private static final Instant NOW = Instant.parse("2026-08-07T12:00:00Z");

    private ConversationQueryService queryService;
    private ConversationModelService modelService;
    private ConversationManagementService managementService;
    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        queryService = org.mockito.Mockito.mock(ConversationQueryService.class);
        modelService = org.mockito.Mockito.mock(ConversationModelService.class);
        managementService = org.mockito.Mockito.mock(
                ConversationManagementService.class
        );
        mockMvc = standaloneSetup(new ConversationController(
                queryService,
                modelService,
                managementService
        ))
                .setControllerAdvice(new GlobalExceptionHandler())
                .build();
    }

    @Test
    void exposesPaginatedConversationList() throws Exception {
        var item = new ConversationResponse(CONVERSATION_ID, "Egg recipe", NOW, NOW);
        when(queryService.listConversations(USER_ID, 1, 5)).thenReturn(
                new PageResponse<>(List.of(item), 1, 5, 6, 2)
        );

        mockMvc.perform(get("/api/conversations?page=1&size=5")
                        .principal(principal()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content[0].id")
                        .value(CONVERSATION_ID.toString()))
                .andExpect(jsonPath("$.page").value(1))
                .andExpect(jsonPath("$.totalElements").value(6));

        verify(queryService).listConversations(USER_ID, 1, 5);
    }

    @Test
    void exposesConversationDetails() throws Exception {
        when(queryService.getConversation(USER_ID, CONVERSATION_ID)).thenReturn(
                new ConversationResponse(CONVERSATION_ID, "Egg recipe", NOW, NOW)
        );

        mockMvc.perform(get("/api/conversations/{id}", CONVERSATION_ID)
                        .principal(principal()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Egg recipe"));
    }

    @Test
    void exposesPaginatedMessageHistory() throws Exception {
        var message = new MessageResponse(
                1L,
                MessageRole.USER,
                "I have eggs",
                null,
                NOW
        );
        when(queryService.listMessages(USER_ID, CONVERSATION_ID, 0, 25)).thenReturn(
                new PageResponse<>(List.of(message), 0, 25, 1, 1)
        );

        mockMvc.perform(get(
                        "/api/conversations/{id}/messages?page=0&size=25",
                        CONVERSATION_ID
                ).principal(principal()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content[0].role").value("USER"))
                .andExpect(jsonPath("$.content[0].content").value("I have eggs"));
    }

    @Test
    void mapsMissingConversationTo404() throws Exception {
        when(queryService.getConversation(USER_ID, CONVERSATION_ID)).thenThrow(
                new ConversationNotFoundException(CONVERSATION_ID)
        );

        mockMvc.perform(get("/api/conversations/{id}", CONVERSATION_ID)
                        .principal(principal()))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("CONVERSATION_NOT_FOUND"));
    }

    @Test
    void explicitlySwitchesOwnedConversationModel() throws Exception {
        var updated = new ConversationResponse(
                CONVERSATION_ID,
                "Egg recipe",
                ModelId.DEEPSEEK_V4_PRO,
                NOW,
                NOW
        );
        when(modelService.changeModel(
                USER_ID, CONVERSATION_ID, ModelId.DEEPSEEK_V4_PRO
        )).thenReturn(updated);

        mockMvc.perform(patch(
                        "/api/conversations/{id}/model",
                        CONVERSATION_ID
                ).principal(principal())
                .contentType(org.springframework.http.MediaType.APPLICATION_JSON)
                .content("{\"modelId\":\"DEEPSEEK_V4_PRO\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.modelId").value("DEEPSEEK_V4_PRO"));

        verify(modelService).changeModel(
                USER_ID, CONVERSATION_ID, ModelId.DEEPSEEK_V4_PRO
        );
    }

    @Test
    void renamesConversationWithoutChangingItsId() throws Exception {
        var updated = new ConversationResponse(
                CONVERSATION_ID,
                "Quick tomato dinner",
                ModelId.STEP_FLASH_3_7,
                NOW,
                NOW.plusSeconds(5)
        );
        when(managementService.rename(
                USER_ID, CONVERSATION_ID, "Quick tomato dinner"
        )).thenReturn(updated);

        mockMvc.perform(patch("/api/conversations/{id}", CONVERSATION_ID)
                        .principal(principal())
                        .contentType(org.springframework.http.MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"Quick tomato dinner\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(CONVERSATION_ID.toString()))
                .andExpect(jsonPath("$.title").value("Quick tomato dinner"));
    }

    @Test
    void rejectsBlankConversationTitle() throws Exception {
        mockMvc.perform(patch("/api/conversations/{id}", CONVERSATION_ID)
                        .principal(principal())
                        .contentType(org.springframework.http.MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"   \"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"));

        verify(managementService, never()).rename(any(), any(), any());
    }

    @Test
    void deletesConversationWithNoResponseBody() throws Exception {
        mockMvc.perform(delete("/api/conversations/{id}", CONVERSATION_ID)
                        .principal(principal()))
                .andExpect(status().isNoContent());

        verify(managementService).delete(USER_ID, CONVERSATION_ID);
    }

    private static UsernamePasswordAuthenticationToken principal() {
        return new UsernamePasswordAuthenticationToken(
                USER_ID.toString(),
                "not-used"
        );
    }
}
