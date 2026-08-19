package com.aicooker.backend.client;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.net.SocketTimeoutException;
import java.net.http.HttpTimeoutException;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import java.util.Arrays;
import java.util.List;
import java.util.function.Consumer;
import java.util.function.Supplier;

import com.aicooker.backend.exception.AiServiceRejectedRequestException;
import com.aicooker.backend.exception.AiServiceServerException;
import com.aicooker.backend.exception.AiServiceTimeoutException;
import com.aicooker.backend.exception.AiServiceUnavailableException;
import com.aicooker.backend.exception.AiThreadRecoveryRequiredException;
import com.aicooker.backend.entity.ModelId;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

@Component
public class RestAiCookerClient implements AiCookerClient {

    private static final Logger LOGGER = LoggerFactory.getLogger(
            RestAiCookerClient.class
    );

    private static final String CHAT_PATH = "/api/v1/chat";
    private static final String STREAM_CHAT_PATH = "/api/v1/chat/stream";
    private static final String RECOVER_CHAT_PATH =
            "/api/v1/internal/chat/recover";
    private static final String RECOVER_STREAM_CHAT_PATH =
            "/api/v1/internal/chat/stream/recover";
    private static final String HEALTH_PATH = "/api/v1/health";
    private static final String MODELS_PATH = "/api/v1/models";
    private static final String FORUM_DRAFTS_PATH = "/api/v1/forum/drafts";
    private static final String MEMORY_EXTRACTION_PATH = "/api/v1/memories/extract";
    private static final String THREAD_STATE_PATH =
            "/api/v1/internal/threads/{threadId}";
    private static final String GENERATED_IMAGE_PATH =
            "/api/v1/internal/generated-images/{generationId}";

    private final RestClient restClient;
    private final ObjectMapper objectMapper;

    public RestAiCookerClient(
            @Qualifier("aiCookerRestClient") RestClient restClient,
            ObjectMapper objectMapper
    ) {
        this.restClient = restClient;
        this.objectMapper = objectMapper;
    }

    @Override
    public void streamChat(
            UUID conversationId,
            String message,
            String imageUrl,
            ModelId modelId,
            List<String> userMemories,
            boolean continuationExpected,
            Consumer<StreamEvent> eventConsumer
    ) {
        var pythonRequest = new PythonChatRequest(
                conversationId.toString(),
                message,
                imageUrl,
                modelId,
                userMemories,
                continuationExpected
        );

        executeStream(STREAM_CHAT_PATH, pythonRequest, eventConsumer);
    }

    @Override
    public void recoverStreamChat(
            UUID conversationId,
            String message,
            String imageUrl,
            ModelId modelId,
            List<String> userMemories,
            List<RecoveryMessage> recoveryHistory,
            Consumer<StreamEvent> eventConsumer
    ) {
        executeStream(
                RECOVER_STREAM_CHAT_PATH,
                new PythonRecoveryRequest(
                        conversationId.toString(),
                        message,
                        imageUrl,
                        modelId,
                        userMemories,
                        false,
                        recoveryHistory
                ),
                eventConsumer
        );
    }

    private void executeStream(
            String path,
            Object pythonRequest,
            Consumer<StreamEvent> eventConsumer
    ) {

        try {
            restClient.post()
                    .uri(path)
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.TEXT_EVENT_STREAM)
                    .body(pythonRequest)
                    .exchange((request, response) -> {
                        requireSuccessfulResponse(response);
                        readEventStream(response.getBody(), eventConsumer);
                        return null;
                    });
        } catch (AiServiceRejectedRequestException
                 | AiServiceServerException exception) {
            throw exception;
        } catch (ResourceAccessException exception) {
            if (hasTimeoutCause(exception)) {
                throw new AiServiceTimeoutException(exception);
            }
            throw new AiServiceUnavailableException(exception);
        } catch (RestClientException exception) {
            throw new AiServiceServerException(
                    "The Python AI stream could not be processed.",
                    exception
            );
        }
    }

    @Override
    public ChatResult chat(
            UUID conversationId,
            String message,
            String imageUrl,
            ModelId modelId,
            List<String> userMemories,
            boolean continuationExpected
    ) {
        var pythonRequest = new PythonChatRequest(
                conversationId.toString(),
                message,
                imageUrl,
                modelId,
                userMemories,
                continuationExpected
        );

        PythonChatResponse pythonResponse = execute(() -> restClient
                .post()
                .uri(CHAT_PATH)
                .body(pythonRequest)
                .retrieve()
                .body(PythonChatResponse.class));

        return toChatResult(pythonResponse);
    }

    @Override
    public ChatResult recoverChat(
            UUID conversationId,
            String message,
            String imageUrl,
            ModelId modelId,
            List<String> userMemories,
            List<RecoveryMessage> recoveryHistory
    ) {
        PythonChatResponse pythonResponse = execute(() -> restClient
                .post()
                .uri(RECOVER_CHAT_PATH)
                .body(new PythonRecoveryRequest(
                        conversationId.toString(),
                        message,
                        imageUrl,
                        modelId,
                        userMemories,
                        false,
                        recoveryHistory
                ))
                .retrieve()
                .body(PythonChatResponse.class));
        return toChatResult(pythonResponse);
    }

    private static ChatResult toChatResult(PythonChatResponse pythonResponse) {
        if (pythonResponse == null
                || pythonResponse.conversationId() == null
                || pythonResponse.answer() == null) {
            throw new AiServiceServerException(
                    "The Python AI service returned an incomplete response."
            );
        }

        try {
            return new ChatResult(
                    UUID.fromString(pythonResponse.conversationId()),
                    pythonResponse.answer(),
                    toGeneratedImageReferences(pythonResponse.generatedImages())
            );
        } catch (IllegalArgumentException exception) {
            throw new AiServiceServerException(
                    "The Python AI service returned an invalid conversation ID.",
                    exception
            );
        }
    }

    private static List<GeneratedImageReference> toGeneratedImageReferences(
            List<PythonGeneratedImage> images
    ) {
        if (images == null || images.isEmpty()) {
            return List.of();
        }
        return images.stream().limit(1).map(image -> {
            if (image.generationId() == null
                    || image.imageModel() == null
                    || image.prompt() == null) {
                throw new AiServiceServerException(
                        "The Python AI service returned incomplete image metadata."
                );
            }
            try {
                return new GeneratedImageReference(
                        UUID.fromString(image.generationId()),
                        image.imageModel(),
                        image.prompt()
                );
            } catch (IllegalArgumentException exception) {
                throw new AiServiceServerException(
                        "The Python AI service returned an invalid generation ID.",
                        exception
                );
            }
        }).toList();
    }

    @Override
    public GeneratedImagePayload downloadGeneratedImage(UUID generationId) {
        return execute(() -> restClient.get()
                .uri(GENERATED_IMAGE_PATH, generationId)
                .accept(MediaType.ALL)
                .exchange((request, response) -> {
                    requireSuccessfulResponse(response);
                    byte[] bytes = response.getBody().readAllBytes();
                    MediaType contentType = response.getHeaders().getContentType();
                    return new GeneratedImagePayload(
                            bytes,
                            contentType == null
                                    ? "application/octet-stream"
                                    : contentType.toString()
                    );
                }));
    }

    @Override
    public boolean isHealthy() {
        PythonHealthResponse response = execute(() -> restClient
                .get()
                .uri(HEALTH_PATH)
                .retrieve()
                .body(PythonHealthResponse.class));

        return response != null && "ok".equalsIgnoreCase(response.status());
    }

    @Override
    public void deleteConversationState(UUID conversationId) {
        var cleanupResponse = execute(() -> restClient
                .delete()
                .uri(THREAD_STATE_PATH, conversationId)
                .retrieve()
                .onStatus(
                        status -> status.value() == 404,
                        (request, response) -> {
                            // A missing thread is already in the desired state.
                        }
                )
                .toBodilessEntity());
        LOGGER.info(
                "conversation_delete operation=PYTHON_THREAD_DELETE "
                        + "conversationId={} status={}",
                conversationId,
                cleanupResponse.getStatusCode().value()
        );
    }

    @Override
    public List<ModelDescriptor> listModels() {
        PythonModelResponse[] response = execute(() -> restClient
                .get()
                .uri(MODELS_PATH)
                .retrieve()
                .body(PythonModelResponse[].class));
        if (response == null) {
            throw new AiServiceServerException(
                    "The Python AI service returned no model catalog."
            );
        }
        return Arrays.stream(response)
                .map(item -> new ModelDescriptor(
                        item.id(),
                        item.displayName(),
                        item.supportsText(),
                        item.supportsTools(),
                        item.supportsStreaming(),
                        item.supportsImages(),
                        item.available()
                ))
                .toList();
    }

    @Override
    public ForumDraftResult generateForumDraft(
            UUID conversationId,
            List<DraftMessage> messages,
            ModelId modelId
    ) {
        PythonForumDraftResponse response = execute(() -> restClient
                .post()
                .uri(FORUM_DRAFTS_PATH)
                .body(new PythonForumDraftRequest(
                        messages,
                        modelId,
                        conversationId.toString()
                ))
                .retrieve()
                .body(PythonForumDraftResponse.class));
        if (response == null
                || response.title() == null
                || response.content() == null
                || response.dishName() == null) {
            throw new AiServiceServerException(
                    "The Python AI service returned an incomplete forum draft."
            );
        }
        return new ForumDraftResult(
                response.title(),
                response.content(),
                response.dishName()
        );
    }

    @Override
    public List<ExtractedMemoryCandidate> extractMemories(
            String currentUserMessage,
            List<MemoryContextMessage> context,
            ModelId modelId
    ) {
        PythonMemoryExtractionResponse response = execute(() -> restClient
                .post()
                .uri(MEMORY_EXTRACTION_PATH)
                .body(new PythonMemoryExtractionRequest(
                        currentUserMessage,
                        context,
                        modelId
                ))
                .retrieve()
                .body(PythonMemoryExtractionResponse.class));
        if (response == null || response.memories() == null) {
            throw new AiServiceServerException(
                    "The Python memory extractor returned an incomplete response."
            );
        }
        return response.memories();
    }

    private <T> T execute(Supplier<T> operation) {
        try {
            return operation.get();
        } catch (ResourceAccessException exception) {
            if (hasTimeoutCause(exception)) {
                throw new AiServiceTimeoutException(exception);
            }
            throw new AiServiceUnavailableException(exception);
        } catch (RestClientResponseException exception) {
            if (isThreadRecoveryRequired(
                    exception.getStatusCode(),
                    exception.getResponseBodyAsString()
            )) {
                throw new AiThreadRecoveryRequiredException(exception);
            }
            if (exception.getStatusCode().is4xxClientError()) {
                throw new AiServiceRejectedRequestException(exception);
            }
            throw new AiServiceServerException(
                    "The Python AI service returned an unsuccessful response.",
                    exception
            );
        } catch (RestClientException exception) {
            throw new AiServiceServerException(
                    "The Python AI service response could not be processed.",
                    exception
            );
        }
    }

    private static boolean hasTimeoutCause(Throwable error) {
        Throwable current = error;
        while (current != null) {
            if (current instanceof SocketTimeoutException
                    || current instanceof HttpTimeoutException) {
                return true;
            }
            current = current.getCause();
        }
        return false;
    }

    private void requireSuccessfulResponse(
            org.springframework.http.client.ClientHttpResponse response
    ) throws IOException {
        HttpStatusCode status = response.getStatusCode();
        if (status.is2xxSuccessful()) {
            return;
        }
        String responseBody = new String(
                response.getBody().readAllBytes(),
                StandardCharsets.UTF_8
        );
        if (isThreadRecoveryRequired(status, responseBody)) {
            throw new AiThreadRecoveryRequiredException(
                    new IllegalStateException(
                            "Python requested one-time thread recovery."
                    )
            );
        }
        if (status.is4xxClientError()) {
            throw new AiServiceRejectedRequestException(
                    new IllegalStateException("Python stream request was rejected.")
            );
        }
        throw new AiServiceServerException(
                "The Python AI streaming endpoint returned an unsuccessful response."
        );
    }

    private static boolean isThreadRecoveryRequired(
            HttpStatusCode status,
            String responseBody
    ) {
        return status.value() == 409
                && responseBody != null
                && responseBody.contains("thread_recovery_required");
    }

    private void readEventStream(
            java.io.InputStream body,
            Consumer<StreamEvent> eventConsumer
    ) {
        boolean terminalEventReceived = false;
        try (var reader = new BufferedReader(new InputStreamReader(
                body,
                StandardCharsets.UTF_8
        ))) {
            String eventName = null;
            var data = new StringBuilder();
            String line;
            while ((line = reader.readLine()) != null) {
                if (line.isEmpty()) {
                    if (data.length() > 0) {
                        StreamEvent event = parseStreamEvent(eventName, data.toString());
                        eventConsumer.accept(event);
                        if ("done".equals(event.type()) || "error".equals(event.type())) {
                            terminalEventReceived = true;
                        }
                    }
                    eventName = null;
                    data.setLength(0);
                    continue;
                }
                if (line.startsWith(":")) {
                    continue;
                }
                if (line.startsWith("event:")) {
                    eventName = line.substring("event:".length()).strip();
                    continue;
                }
                if (line.startsWith("data:")) {
                    if (data.length() > 0) {
                        data.append('\n');
                    }
                    data.append(line.substring("data:".length()).stripLeading());
                }
            }

            if (data.length() > 0) {
                StreamEvent event = parseStreamEvent(eventName, data.toString());
                eventConsumer.accept(event);
                terminalEventReceived = "done".equals(event.type())
                        || "error".equals(event.type());
            }
        } catch (IOException exception) {
            throw new AiServiceServerException(
                    "The Python AI stream ended unexpectedly.",
                    exception
            );
        }

        if (!terminalEventReceived) {
            throw new AiServiceServerException(
                    "The Python AI stream ended without a terminal event."
            );
        }
    }

    private StreamEvent parseStreamEvent(String eventName, String json) {
        final PythonStreamEvent source;
        try {
            source = objectMapper.readValue(json, PythonStreamEvent.class);
        } catch (JsonProcessingException exception) {
            throw new AiServiceServerException(
                    "The Python AI stream returned an invalid event.",
                    exception
            );
        }

        String type = source.type() == null ? eventName : source.type();
        if (type == null || !(type.equals("status")
                || type.equals("token")
                || type.equals("generated_image")
                || type.equals("image_error")
                || type.equals("done")
                || type.equals("error"))) {
            throw new AiServiceServerException(
                    "The Python AI stream returned an unsupported event."
            );
        }
        return new StreamEvent(
                type,
                source.stage(),
                source.message(),
                source.content(),
                parseGenerationId(source.generationId()),
                source.imageModel(),
                source.prompt()
        );
    }

    private static UUID parseGenerationId(String value) {
        if (value == null) {
            return null;
        }
        try {
            return UUID.fromString(value);
        } catch (IllegalArgumentException exception) {
            throw new AiServiceServerException(
                    "The Python AI stream returned an invalid generation ID.",
                    exception
            );
        }
    }

    private record PythonChatRequest(
            @JsonProperty("conversation_id") String conversationId,
            String message,
            @JsonProperty("image_url") String imageUrl,
            @JsonProperty("model_id") ModelId modelId,
            @JsonProperty("user_memories") List<String> userMemories,
            @JsonProperty("continuation_expected") boolean continuationExpected
    ) {
    }

    private record PythonRecoveryRequest(
            @JsonProperty("conversation_id") String conversationId,
            String message,
            @JsonProperty("image_url") String imageUrl,
            @JsonProperty("model_id") ModelId modelId,
            @JsonProperty("user_memories") List<String> userMemories,
            @JsonProperty("continuation_expected") boolean continuationExpected,
            @JsonProperty("recovery_history") List<RecoveryMessage> recoveryHistory
    ) {
    }

    private record PythonChatResponse(
            @JsonProperty("conversation_id") String conversationId,
            String answer,
            @JsonProperty("generated_images") List<PythonGeneratedImage> generatedImages
    ) {
    }

    private record PythonGeneratedImage(
            @JsonProperty("generation_id") String generationId,
            @JsonProperty("image_model") String imageModel,
            String prompt
    ) {
    }

    private record PythonStreamEvent(
            String type,
            String stage,
            String message,
            String content,
            @JsonProperty("generation_id") String generationId,
            @JsonProperty("image_model") String imageModel,
            String prompt
    ) {
    }

    private record PythonHealthResponse(String status) {
    }

    private record PythonModelResponse(
            ModelId id,
            @JsonProperty("display_name") String displayName,
            @JsonProperty("supports_text") boolean supportsText,
            @JsonProperty("supports_tools") boolean supportsTools,
            @JsonProperty("supports_streaming") boolean supportsStreaming,
            @JsonProperty("supports_images") boolean supportsImages,
            boolean available
    ) {
    }

    private record PythonForumDraftRequest(
            List<DraftMessage> messages,
            @JsonProperty("model_id") ModelId modelId,
            @JsonProperty("conversation_id") String conversationId
    ) {
    }

    private record PythonForumDraftResponse(
            String title,
            String content,
            @JsonProperty("dish_name") String dishName
    ) {
    }

    private record PythonMemoryExtractionRequest(
            @JsonProperty("current_user_message") String currentUserMessage,
            List<MemoryContextMessage> context,
            @JsonProperty("model_id") ModelId modelId
    ) {
    }

    private record PythonMemoryExtractionResponse(
            List<ExtractedMemoryCandidate> memories
    ) {
    }
}
