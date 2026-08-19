package com.aicooker.backend.service;

import java.io.ByteArrayInputStream;
import java.net.URI;
import java.time.Clock;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import com.aicooker.backend.client.AiCookerClient;
import com.aicooker.backend.dto.GeneratedImageResponse;
import com.aicooker.backend.entity.GeneratedImageEntity;
import com.aicooker.backend.entity.MessageRole;
import com.aicooker.backend.exception.GeneratedImageNotFoundException;
import com.aicooker.backend.exception.ImageStorageException;
import com.aicooker.backend.repository.ConversationRepository;
import com.aicooker.backend.repository.GeneratedImageRepository;
import com.aicooker.backend.repository.MessageRepository;
import com.aicooker.backend.repository.UserRepository;
import com.aicooker.backend.storage.ImageObjectStorage;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class GeneratedImageService {

    private static final Logger LOGGER = LoggerFactory.getLogger(
            GeneratedImageService.class
    );
    private static final long MAX_GENERATED_IMAGE_SIZE = 20L * 1024 * 1024;
    private static final Map<String, String> EXTENSIONS = Map.of(
            "image/jpeg", "jpg",
            "image/png", "png",
            "image/webp", "webp"
    );

    private final AiCookerClient aiCookerClient;
    private final ImageObjectStorage objectStorage;
    private final GeneratedImageRepository generatedImageRepository;
    private final UserRepository userRepository;
    private final ConversationRepository conversationRepository;
    private final MessageRepository messageRepository;
    private final Clock clock;

    public GeneratedImageService(
            AiCookerClient aiCookerClient,
            ImageObjectStorage objectStorage,
            GeneratedImageRepository generatedImageRepository,
            UserRepository userRepository,
            ConversationRepository conversationRepository,
            MessageRepository messageRepository,
            Clock clock
    ) {
        this.aiCookerClient = aiCookerClient;
        this.objectStorage = objectStorage;
        this.generatedImageRepository = generatedImageRepository;
        this.userRepository = userRepository;
        this.conversationRepository = conversationRepository;
        this.messageRepository = messageRepository;
        this.clock = clock;
    }

    @Transactional
    public GeneratedImageResponse store(
            UUID userId,
            UUID conversationId,
            Long assistantMessageId,
            AiCookerClient.GeneratedImageReference reference
    ) {
        var owner = userRepository.findById(userId)
                .orElseThrow(() -> new AccessDeniedException(
                        "Authenticated user no longer exists."
                ));
        var conversation = conversationRepository
                .findByIdAndUser_Id(conversationId, userId)
                .orElseThrow(() -> new AccessDeniedException(
                        "Conversation is not owned by the current user."
                ));
        var assistantMessage = messageRepository.findById(assistantMessageId)
                .filter(message -> message.getConversation().getId()
                        .equals(conversationId))
                .filter(message -> message.getRole() == MessageRole.ASSISTANT)
                .orElseThrow(() -> new ImageStorageException(
                        "Generated image has no valid assistant message."
                ));

        AiCookerClient.GeneratedImagePayload payload =
                aiCookerClient.downloadGeneratedImage(reference.generationId());
        ValidatedPayload validated = validate(payload);
        UUID imageId = UUID.randomUUID();
        String objectKey = "users/%s/generated/%s.%s".formatted(
                userId,
                imageId,
                validated.extension()
        );
        boolean uploaded = false;
        try {
            objectStorage.upload(
                    objectKey,
                    new ByteArrayInputStream(payload.bytes()),
                    payload.bytes().length,
                    validated.contentType()
            );
            uploaded = true;
            var entity = generatedImageRepository.saveAndFlush(
                    new GeneratedImageEntity(
                            imageId,
                            owner,
                            conversation,
                            assistantMessage,
                            objectKey,
                            reference.imageModel(),
                            reference.prompt(),
                            validated.contentType(),
                            payload.bytes().length,
                            clock.instant()
                    )
            );
            URI readUrl = objectStorage.createReadUrl(objectKey);
            return toResponse(entity, readUrl);
        } catch (RuntimeException exception) {
            if (uploaded) {
                cleanupOrphan(objectKey);
            }
            throw exception;
        }
    }

    @Transactional(readOnly = true)
    public GeneratedImageResponse get(UUID userId, UUID imageId) {
        GeneratedImageEntity image = generatedImageRepository
                .findByIdAndUser_Id(imageId, userId)
                .orElseThrow(() -> new GeneratedImageNotFoundException(imageId));
        return createResponse(image);
    }

    @Transactional(readOnly = true)
    public Map<Long, List<GeneratedImageResponse>> forMessages(
            UUID userId,
            List<Long> messageIds
    ) {
        if (messageIds.isEmpty()) {
            return Map.of();
        }
        Map<Long, List<GeneratedImageResponse>> result = new LinkedHashMap<>();
        for (GeneratedImageEntity image : generatedImageRepository
                .findByAssistantMessage_IdInOrderByCreatedAtAscIdAsc(messageIds)) {
            if (!image.getUser().getId().equals(userId)) {
                continue;
            }
            try {
                result.computeIfAbsent(
                        image.getAssistantMessage().getId(),
                        ignored -> new ArrayList<>()
                ).add(createResponse(image));
            } catch (ImageStorageException exception) {
                LOGGER.warn(
                        "generated_image_history_unavailable imageId={} exception={}",
                        image.getId(),
                        exception.getClass().getSimpleName()
                );
            }
        }
        return result;
    }

    private GeneratedImageResponse createResponse(GeneratedImageEntity image) {
        if (!objectStorage.exists(image.getObjectKey())) {
            throw new ImageStorageException(
                    "Generated image metadata exists but its OSS object is missing."
            );
        }
        return toResponse(
                image,
                objectStorage.createReadUrl(image.getObjectKey())
        );
    }

    private static ValidatedPayload validate(
            AiCookerClient.GeneratedImagePayload payload
    ) {
        if (payload == null || payload.bytes() == null) {
            throw new ImageStorageException("Python returned no generated image.");
        }
        byte[] bytes = payload.bytes();
        if (bytes.length == 0 || bytes.length > MAX_GENERATED_IMAGE_SIZE) {
            throw new ImageStorageException(
                    "Python returned an invalid generated image size."
            );
        }
        String contentType = payload.contentType() == null
                ? "" : payload.contentType().toLowerCase();
        String extension = EXTENSIONS.get(contentType);
        if (extension == null || !matchesSignature(contentType, bytes)) {
            throw new ImageStorageException(
                    "Python returned an unsupported generated image."
            );
        }
        return new ValidatedPayload(contentType, extension);
    }

    private static boolean matchesSignature(String contentType, byte[] bytes) {
        return switch (contentType) {
            case "image/jpeg" -> bytes.length >= 3
                    && Byte.toUnsignedInt(bytes[0]) == 0xFF
                    && Byte.toUnsignedInt(bytes[1]) == 0xD8
                    && Byte.toUnsignedInt(bytes[2]) == 0xFF;
            case "image/png" -> bytes.length >= 8
                    && Byte.toUnsignedInt(bytes[0]) == 0x89
                    && bytes[1] == 0x50 && bytes[2] == 0x4E
                    && bytes[3] == 0x47 && bytes[4] == 0x0D
                    && bytes[5] == 0x0A && bytes[6] == 0x1A
                    && bytes[7] == 0x0A;
            case "image/webp" -> bytes.length >= 12
                    && new String(bytes, 0, 4, java.nio.charset.StandardCharsets.US_ASCII)
                    .equals("RIFF")
                    && new String(bytes, 8, 4, java.nio.charset.StandardCharsets.US_ASCII)
                    .equals("WEBP");
            default -> false;
        };
    }

    private void cleanupOrphan(String objectKey) {
        try {
            objectStorage.delete(objectKey);
        } catch (ImageStorageException cleanupFailure) {
            LOGGER.error(
                    "generated_image_orphan_cleanup_failed objectKey={} exception={}",
                    objectKey,
                    cleanupFailure.getClass().getSimpleName()
            );
        }
    }

    private static GeneratedImageResponse toResponse(
            GeneratedImageEntity image,
            URI readUrl
    ) {
        return new GeneratedImageResponse(
                image.getId(),
                readUrl.toString(),
                image.getImageModel(),
                image.getCreatedAt()
        );
    }

    private record ValidatedPayload(String contentType, String extension) {
    }
}
