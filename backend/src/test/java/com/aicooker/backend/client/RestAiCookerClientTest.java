package com.aicooker.backend.client;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.http.HttpMethod.GET;
import static org.springframework.http.HttpMethod.POST;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import java.net.ConnectException;
import java.net.InetSocketAddress;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import com.aicooker.backend.exception.AiServiceRejectedRequestException;
import com.aicooker.backend.exception.AiServiceServerException;
import com.aicooker.backend.exception.AiServiceTimeoutException;
import com.aicooker.backend.exception.AiServiceUnavailableException;
import com.aicooker.backend.exception.AiThreadRecoveryRequiredException;
import com.aicooker.backend.entity.ModelId;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

class RestAiCookerClientTest {

    private MockRestServiceServer server;
    private RestAiCookerClient client;

    @BeforeEach
    void setUp() {
        RestClient.Builder builder = RestClient.builder();
        server = MockRestServiceServer.bindTo(builder).build();
        client = new RestAiCookerClient(
                builder.baseUrl("http://python-ai.test").build(),
                new ObjectMapper()
        );
    }

    @Test
    void mapsJavaRequestToPythonContractAndMapsResponseBack() {
        UUID conversationId = UUID.fromString("9b677223-0733-4d89-b13a-33f2a08ea610");
        server.expect(requestTo("http://python-ai.test/api/v1/chat"))
                .andExpect(method(POST))
                .andExpect(content().json("""
                        {
                          "conversation_id": "9b677223-0733-4d89-b13a-33f2a08ea610",
                          "message": "I have eggs",
                          "image_url": "https://images.example/ingredients.jpg",
                          "model_id": "DEEPSEEK_V4_PRO",
                          "user_memories": ["Cooking preference — oil: low"]
                        }
                        """))
                .andRespond(withSuccess("""
                        {
                          "conversation_id": "9b677223-0733-4d89-b13a-33f2a08ea610",
                          "answer": "Cook an omelette"
                        }
                        """, MediaType.APPLICATION_JSON));

        AiCookerClient.ChatResult result = client.chat(
                conversationId,
                "I have eggs",
                "https://images.example/ingredients.jpg",
                ModelId.DEEPSEEK_V4_PRO,
                List.of("Cooking preference — oil: low")
        );

        assertThat(result.conversationId()).isEqualTo(conversationId);
        assertThat(result.answer()).isEqualTo("Cook an omelette");
        server.verify();
    }

    @Test
    void mapsGeneratedImageMetadataAndDownloadsOnlyFromInternalEndpoint() {
        UUID conversationId = UUID.fromString(
                "9b677223-0733-4d89-b13a-33f2a08ea610"
        );
        UUID generationId = UUID.fromString(
                "26806f88-d8fe-4de2-972a-c4482458f134"
        );
        server.expect(requestTo("http://python-ai.test/api/v1/chat"))
                .andRespond(withSuccess("""
                        {
                          "conversation_id":"9b677223-0733-4d89-b13a-33f2a08ea610",
                          "answer":"Here is the dish.",
                          "generated_images":[{
                            "generation_id":"26806f88-d8fe-4de2-972a-c4482458f134",
                            "image_model":"step-image-edit-2",
                            "prompt":"A realistic food photo"
                          }]
                        }
                        """, MediaType.APPLICATION_JSON));
        server.expect(requestTo(
                        "http://python-ai.test/api/v1/internal/generated-images/"
                                + generationId
                ))
                .andExpect(method(GET))
                .andRespond(withSuccess(
                        new byte[] {(byte) 0xFF, (byte) 0xD8, (byte) 0xFF},
                        MediaType.IMAGE_JPEG
                ));

        var result = client.chat(conversationId, "show it", null);
        var payload = client.downloadGeneratedImage(generationId);

        assertThat(result.generatedImages()).singleElement().satisfies(image -> {
            assertThat(image.generationId()).isEqualTo(generationId);
            assertThat(image.imageModel()).isEqualTo("step-image-edit-2");
        });
        assertThat(payload.contentType()).isEqualTo("image/jpeg");
        assertThat(payload.bytes()).hasSize(3);
        server.verify();
    }

    @Test
    void mapsPythonHealthResponse() {
        server.expect(requestTo("http://python-ai.test/api/v1/health"))
                .andExpect(method(GET))
                .andRespond(withSuccess("{\"status\":\"ok\"}", MediaType.APPLICATION_JSON));

        assertThat(client.isHealthy()).isTrue();
        server.verify();
    }

    @Test
    void mapsPythonModelCatalogWithoutProviderConfiguration() {
        server.expect(requestTo("http://python-ai.test/api/v1/models"))
                .andExpect(method(GET))
                .andRespond(withSuccess("""
                        [{
                          "id": "DEEPSEEK_V4_PRO",
                          "display_name": "DeepSeek V4 Pro",
                          "supports_text": true,
                          "supports_tools": true,
                          "supports_streaming": true,
                          "supports_images": false,
                          "available": true
                        }]
                        """, MediaType.APPLICATION_JSON));

        List<AiCookerClient.ModelDescriptor> models = client.listModels();

        assertThat(models).hasSize(1);
        assertThat(models.getFirst().id()).isEqualTo(ModelId.DEEPSEEK_V4_PRO);
        assertThat(models.getFirst().supportsImages()).isFalse();
        server.verify();
    }

    @Test
    void mapsOrderedForumHistoryAndModelToPythonDraftContract() {
        UUID conversationId = UUID.fromString(
                "d54d970b-cf39-4112-9ad5-a4d1e5411f60"
        );
        server.expect(requestTo("http://python-ai.test/api/v1/forum/drafts"))
                .andExpect(method(POST))
                .andExpect(content().json("""
                        {
                          "messages": [
                            {"role":"USER","content":"I have eggs."},
                            {"role":"ASSISTANT","content":"Make an omelette."}
                          ],
                          "model_id":"DEEPSEEK_V4_PRO",
                          "conversation_id":"d54d970b-cf39-4112-9ad5-a4d1e5411f60"
                        }
                        """))
                .andRespond(withSuccess("""
                        {
                          "title":"Easy Omelette",
                          "content":"A grounded omelette recommendation.",
                          "dish_name":"Omelette"
                        }
                        """, MediaType.APPLICATION_JSON));

        var result = client.generateForumDraft(
                conversationId,
                List.of(
                        new AiCookerClient.DraftMessage("USER", "I have eggs."),
                        new AiCookerClient.DraftMessage(
                                "ASSISTANT", "Make an omelette."
                        )
                ),
                ModelId.DEEPSEEK_V4_PRO
        );

        assertThat(result.title()).isEqualTo("Easy Omelette");
        assertThat(result.dishName()).isEqualTo("Omelette");
        server.verify();
    }

    @Test
    void mapsGroundedMemoryExtractionContract() {
        server.expect(requestTo("http://python-ai.test/api/v1/memories/extract"))
                .andExpect(method(POST))
                .andExpect(content().json("""
                        {
                          "current_user_message":"I prefer less oil.",
                          "context":[
                            {"role":"USER","content":"I prefer less oil."},
                            {"role":"ASSISTANT","content":"I will keep it light."}
                          ],
                          "model_id":"STEP_FLASH_3_7"
                        }
                        """))
                .andRespond(withSuccess("""
                        {"memories":[{
                          "action":"UPSERT",
                          "memory_type":"COOKING_PREFERENCE",
                          "key":"oil",
                          "value":"low",
                          "confidence":0.96,
                          "source_text":"I prefer less oil"
                        }]}
                        """, MediaType.APPLICATION_JSON));

        var result = client.extractMemories(
                "I prefer less oil.",
                List.of(
                        new AiCookerClient.MemoryContextMessage(
                                "USER", "I prefer less oil."
                        ),
                        new AiCookerClient.MemoryContextMessage(
                                "ASSISTANT", "I will keep it light."
                        )
                ),
                ModelId.STEP_FLASH_3_7
        );

        assertThat(result).singleElement().satisfies(memory -> {
            assertThat(memory.memoryType().name())
                    .isEqualTo("COOKING_PREFERENCE");
            assertThat(memory.sourceText()).isEqualTo("I prefer less oil");
        });
        server.verify();
    }

    @Test
    void mapsReadTimeout() {
        server.expect(requestTo("http://python-ai.test/api/v1/chat"))
                .andRespond(request -> {
                    throw new SocketTimeoutException("Read timed out");
                });

        assertThatThrownBy(() -> client.chat(UUID.randomUUID(), "hello", null))
                .isInstanceOf(AiServiceTimeoutException.class);
        server.verify();
    }

    @Test
    void mapsUnavailableService() {
        server.expect(requestTo("http://python-ai.test/api/v1/chat"))
                .andRespond(request -> {
                    throw new ConnectException("Connection refused");
                });

        assertThatThrownBy(() -> client.chat(UUID.randomUUID(), "hello", null))
                .isInstanceOf(AiServiceUnavailableException.class);
        server.verify();
    }

    @Test
    void mapsPython4xxResponse() {
        server.expect(requestTo("http://python-ai.test/api/v1/chat"))
                .andRespond(withStatus(HttpStatus.BAD_REQUEST));

        assertThatThrownBy(() -> client.chat(UUID.randomUUID(), "hello", null))
                .isInstanceOf(AiServiceRejectedRequestException.class);
        server.verify();
    }

    @Test
    void mapsRecoveryConflictAndThenSendsAuthorizedBusinessHistory() {
        UUID conversationId = UUID.fromString(
                "9b677223-0733-4d89-b13a-33f2a08ea610"
        );
        server.expect(requestTo("http://python-ai.test/api/v1/chat"))
                .andExpect(method(POST))
                .andExpect(content().json("""
                        {"continuation_expected":true}
                        """, false))
                .andRespond(withStatus(HttpStatus.CONFLICT)
                        .contentType(MediaType.APPLICATION_JSON)
                        .body("""
                                {"detail":{
                                  "code":"thread_recovery_required",
                                  "reason":"historical_image"
                                }}
                                """));

        server.expect(requestTo(
                        "http://python-ai.test/api/v1/internal/chat/recover"
                ))
                .andExpect(method(POST))
                .andExpect(content().json("""
                        {
                          "conversation_id":"9b677223-0733-4d89-b13a-33f2a08ea610",
                          "message":"continue",
                          "recovery_history":[
                            {"message_id":10,"role":"USER","content":"Earlier"},
                            {"message_id":11,"role":"ASSISTANT","content":"Answer"}
                          ]
                        }
                        """))
                .andRespond(withSuccess("""
                        {
                          "conversation_id":"9b677223-0733-4d89-b13a-33f2a08ea610",
                          "answer":"Continued answer"
                        }
                        """, MediaType.APPLICATION_JSON));

        assertThatThrownBy(() -> client.chat(
                conversationId,
                "continue",
                null,
                ModelId.STEP_FLASH_3_7,
                List.of(),
                true
        )).isInstanceOf(AiThreadRecoveryRequiredException.class);

        var recovered = client.recoverChat(
                conversationId,
                "continue",
                null,
                ModelId.STEP_FLASH_3_7,
                List.of(),
                List.of(
                        new AiCookerClient.RecoveryMessage(
                                10L, "USER", "Earlier"
                        ),
                        new AiCookerClient.RecoveryMessage(
                                11L, "ASSISTANT", "Answer"
                        )
                )
        );

        assertThat(recovered.conversationId()).isEqualTo(conversationId);
        assertThat(recovered.answer()).isEqualTo("Continued answer");
        server.verify();
    }

    @Test
    void mapsPython5xxResponse() {
        server.expect(requestTo("http://python-ai.test/api/v1/chat"))
                .andRespond(withStatus(HttpStatus.SERVICE_UNAVAILABLE));

        assertThatThrownBy(() -> client.chat(UUID.randomUUID(), "hello", null))
                .isInstanceOf(AiServiceServerException.class);
        server.verify();
    }

    @Test
    void deletesOnlyTheRequestedPythonThreadState() {
        UUID conversationId = UUID.fromString(
                "9b677223-0733-4d89-b13a-33f2a08ea610"
        );
        server.expect(requestTo(
                        "http://python-ai.test/api/v1/internal/threads/"
                                + conversationId
                ))
                .andExpect(method(org.springframework.http.HttpMethod.DELETE))
                .andRespond(withStatus(HttpStatus.NO_CONTENT));

        client.deleteConversationState(conversationId);

        server.verify();
    }

    @Test
    void missingPythonThreadIsAlreadySuccessfullyDeleted() {
        UUID conversationId = UUID.fromString(
                "9b677223-0733-4d89-b13a-33f2a08ea610"
        );
        server.expect(requestTo(
                        "http://python-ai.test/api/v1/internal/threads/"
                                + conversationId
                ))
                .andExpect(method(org.springframework.http.HttpMethod.DELETE))
                .andRespond(withStatus(HttpStatus.NOT_FOUND));

        client.deleteConversationState(conversationId);

        server.verify();
    }

    @Test
    void mapsPythonSseEventsWithoutExposingSnakeCase() {
        UUID conversationId = UUID.fromString(
                "9b677223-0733-4d89-b13a-33f2a08ea610"
        );
        server.expect(requestTo("http://python-ai.test/api/v1/chat/stream"))
                .andExpect(method(POST))
                .andExpect(content().json("""
                        {
                          "conversation_id": "9b677223-0733-4d89-b13a-33f2a08ea610",
                          "message": "I have eggs",
                          "image_url": null
                        }
                        """))
                .andRespond(withSuccess("""
                        event: status
                        data: {"type":"status","stage":"thinking","message":"Thinking..."}

                        event: token
                        data: {"type":"token","content":"Cook "}

                        event: token
                        data: {"type":"token","content":"eggs."}

                        event: generated_image
                        data: {"type":"generated_image","generation_id":"26806f88-d8fe-4de2-972a-c4482458f134","image_model":"step-image-edit-2","prompt":"A food photo"}

                        event: done
                        data: {"type":"done"}

                        """, MediaType.TEXT_EVENT_STREAM));

        List<AiCookerClient.StreamEvent> events = new ArrayList<>();
        client.streamChat(conversationId, "I have eggs", null, events::add);

        assertThat(events).extracting(AiCookerClient.StreamEvent::type)
                .containsExactly(
                        "status", "token", "token", "generated_image", "done"
                );
        assertThat(events).extracting(AiCookerClient.StreamEvent::content)
                .containsExactly(null, "Cook ", "eggs.", null, null);
        assertThat(events.get(3).imageModel()).isEqualTo("step-image-edit-2");
        server.verify();
    }

    @Test
    void forwardsFirstPythonEventBeforePythonCompletes() throws Exception {
        HttpServer streamingServer = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0),
                0
        );
        CountDownLatch firstEventWritten = new CountDownLatch(1);
        CountDownLatch releaseCompletion = new CountDownLatch(1);
        CountDownLatch firstEventReceived = new CountDownLatch(1);
        streamingServer.createContext("/api/v1/chat/stream", exchange -> {
            exchange.getRequestBody().readAllBytes();
            exchange.getResponseHeaders().add(
                    "Content-Type",
                    MediaType.TEXT_EVENT_STREAM_VALUE
            );
            exchange.sendResponseHeaders(200, 0);
            try (var output = exchange.getResponseBody()) {
                output.write(("""
                        event: status
                        data: {"type":"status","stage":"thinking","message":"Thinking..."}

                        """).getBytes(StandardCharsets.UTF_8));
                output.flush();
                firstEventWritten.countDown();
                releaseCompletion.await(5, TimeUnit.SECONDS);
                output.write(("""
                        event: token
                        data: {"type":"token","content":"Done"}

                        event: done
                        data: {"type":"done"}

                        """).getBytes(StandardCharsets.UTF_8));
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
            }
        });
        streamingServer.start();

        try {
            var streamingClient = new RestAiCookerClient(
                    RestClient.builder()
                            .baseUrl("http://127.0.0.1:"
                                    + streamingServer.getAddress().getPort())
                            .build(),
                    new ObjectMapper()
            );
            CompletableFuture<Void> request = CompletableFuture.runAsync(() ->
                    streamingClient.streamChat(
                            UUID.randomUUID(),
                            "hello",
                            null,
                            event -> firstEventReceived.countDown()
                    )
            );

            assertThat(firstEventWritten.await(2, TimeUnit.SECONDS)).isTrue();
            assertThat(firstEventReceived.await(2, TimeUnit.SECONDS)).isTrue();
            assertThat(request).isNotCompleted();
            releaseCompletion.countDown();
            request.get(5, TimeUnit.SECONDS);
        } finally {
            releaseCompletion.countDown();
            streamingServer.stop(0);
        }
    }
}
