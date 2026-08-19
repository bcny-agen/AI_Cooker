package com.aicooker.backend.controller;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.setup.MockMvcBuilders.standaloneSetup;

import java.net.ConnectException;
import java.net.SocketTimeoutException;
import java.util.UUID;

import com.aicooker.backend.dto.ChatRequest;
import com.aicooker.backend.dto.ChatResponse;
import com.aicooker.backend.dto.ChatStreamEvent;
import com.aicooker.backend.exception.AiServiceRejectedRequestException;
import com.aicooker.backend.exception.AiServiceServerException;
import com.aicooker.backend.exception.AiServiceTimeoutException;
import com.aicooker.backend.exception.AiServiceUnavailableException;
import com.aicooker.backend.exception.GlobalExceptionHandler;
import com.aicooker.backend.service.ChatService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.test.web.servlet.MockMvc;

class ChatControllerTest {

    private static final UUID USER_ID =
            UUID.fromString("0f0c2f0d-a51b-44f6-915b-ed9d3f583804");

    private ChatService chatService;
    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        chatService = org.mockito.Mockito.mock(ChatService.class);
        mockMvc = standaloneSetup(new ChatController(chatService, Runnable::run))
                .setControllerAdvice(new GlobalExceptionHandler())
                .build();
    }

    @Test
    void exposesJavaChatEndpoint() throws Exception {
        UUID conversationId = UUID.fromString("9b677223-0733-4d89-b13a-33f2a08ea610");
        when(chatService.chat(eq(USER_ID), any(ChatRequest.class))).thenReturn(
                new ChatResponse(conversationId, "Make tomato scrambled eggs")
        );

        mockMvc.perform(post("/api/chat")
                        .principal(principal())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "conversationId": "9b677223-0733-4d89-b13a-33f2a08ea610",
                                  "message": "I have eggs and tomatoes",
                                  "imageId": null
                                }
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.conversationId").value(conversationId.toString()))
                .andExpect(jsonPath("$.answer").value("Make tomato scrambled eggs"));

        verify(chatService).chat(eq(USER_ID), any(ChatRequest.class));
    }

    @Test
    void returns400ForValidationErrors() throws Exception {
        mockMvc.perform(post("/api/chat")
                        .principal(principal())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "message": "valid message",
                                  "imageId": "not-a-uuid"
                                }
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.status").value(400))
                .andExpect(jsonPath("$.path").value("/api/chat"));

        verify(chatService, never()).chat(any(UUID.class), any(ChatRequest.class));
    }

    @Test
    void mapsUnavailableAiService() throws Exception {
        when(chatService.chat(eq(USER_ID), any(ChatRequest.class))).thenThrow(
                new AiServiceUnavailableException(new ConnectException("refused"))
        );

        mockMvc.perform(validChatRequest())
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.code").value("AI_SERVICE_UNAVAILABLE"));
    }

    @Test
    void mapsAiTimeout() throws Exception {
        when(chatService.chat(eq(USER_ID), any(ChatRequest.class))).thenThrow(
                new AiServiceTimeoutException(new SocketTimeoutException("timeout"))
        );

        mockMvc.perform(validChatRequest())
                .andExpect(status().isGatewayTimeout())
                .andExpect(jsonPath("$.code").value("AI_SERVICE_TIMEOUT"));
    }

    @Test
    void mapsPython4xxResponse() throws Exception {
        when(chatService.chat(eq(USER_ID), any(ChatRequest.class))).thenThrow(
                new AiServiceRejectedRequestException(new RuntimeException("python 400"))
        );

        mockMvc.perform(validChatRequest())
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("AI_REQUEST_REJECTED"));
    }

    @Test
    void mapsPython5xxResponse() throws Exception {
        when(chatService.chat(eq(USER_ID), any(ChatRequest.class))).thenThrow(
                new AiServiceServerException("python 500")
        );

        mockMvc.perform(validChatRequest())
                .andExpect(status().isBadGateway())
                .andExpect(jsonPath("$.code").value("AI_SERVICE_ERROR"));
    }

    @Test
    void mapsUnexpectedBackendErrorWithoutExposingDetails() throws Exception {
        when(chatService.chat(eq(USER_ID), any(ChatRequest.class))).thenThrow(
                new IllegalStateException("secret internal detail")
        );

        mockMvc.perform(validChatRequest())
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.code").value("INTERNAL_ERROR"))
                .andExpect(jsonPath("$.message").value(
                        "An unexpected backend error occurred."
                ));
    }

    @Test
    void exposesStreamingSseEndpoint() throws Exception {
        UUID conversationId = UUID.fromString(
                "9b677223-0733-4d89-b13a-33f2a08ea610"
        );
        var session = new ChatService.StreamSession(
                USER_ID,
                conversationId,
                "I have eggs",
                null
        );
        when(chatService.beginStream(eq(USER_ID), any(ChatRequest.class)))
                .thenReturn(session);
        doAnswer(invocation -> {
            @SuppressWarnings("unchecked")
            var consumer = (java.util.function.Consumer<ChatStreamEvent>)
                    invocation.getArgument(1);
            consumer.accept(ChatStreamEvent.status(
                    conversationId,
                    "thinking",
                    "Thinking about your ingredients..."
            ));
            consumer.accept(ChatStreamEvent.token(conversationId, "Cook eggs."));
            consumer.accept(ChatStreamEvent.done(conversationId));
            return null;
        }).when(chatService).stream(eq(session), any());

        var result = mockMvc.perform(post("/api/chat/stream")
                        .principal(principal())
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.TEXT_EVENT_STREAM)
                        .content("""
                                {
                                  "message": "I have eggs",
                                  "imageId": null
                                }
                                """))
                .andExpect(request().asyncStarted())
                .andReturn();

        mockMvc.perform(asyncDispatch(result))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.TEXT_EVENT_STREAM
                ))
                .andExpect(content().string(org.hamcrest.Matchers.containsString(
                        "event:token"
                )))
                .andExpect(content().string(org.hamcrest.Matchers.containsString(
                        conversationId.toString()
                )));
    }

    private static org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder
            validChatRequest() {
        return post("/api/chat")
                .principal(principal())
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {
                          "message": "I have eggs",
                          "imageId": null
                        }
                        """);
    }

    private static UsernamePasswordAuthenticationToken principal() {
        return new UsernamePasswordAuthenticationToken(
                USER_ID.toString(),
                "not-used"
        );
    }
}
