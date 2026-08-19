package com.aicooker.backend.service;

import java.text.Normalizer;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.UUID;
import java.util.regex.Pattern;

import com.aicooker.backend.client.AiCookerClient;
import com.aicooker.backend.entity.MessageEntity;
import com.aicooker.backend.entity.ModelId;
import com.aicooker.backend.repository.MessageRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class MemoryExtractionService {

    private static final Logger LOGGER = LoggerFactory.getLogger(
            MemoryExtractionService.class
    );
    private static final Pattern WHITESPACE = Pattern.compile("\\s+");

    private final AiCookerClient aiCookerClient;
    private final MessageRepository messageRepository;
    private final UserMemoryService userMemoryService;

    public MemoryExtractionService(
            AiCookerClient aiCookerClient,
            MessageRepository messageRepository,
            UserMemoryService userMemoryService
    ) {
        this.aiCookerClient = aiCookerClient;
        this.messageRepository = messageRepository;
        this.userMemoryService = userMemoryService;
    }

    public void extractSafely(
            UUID userId,
            UUID conversationId,
            String currentUserMessage,
            ModelId modelId
    ) {
        try {
            List<MessageEntity> recent = messageRepository
                    .findTop8ByConversation_IdOrderByCreatedAtDescIdDesc(
                            conversationId
                    );
            Collections.reverse(recent);
            List<AiCookerClient.MemoryContextMessage> context = recent.stream()
                    .map(message -> new AiCookerClient.MemoryContextMessage(
                            message.getRole().name(),
                            message.getContent()
                    ))
                    .toList();
            List<AiCookerClient.ExtractedMemoryCandidate> extracted =
                    aiCookerClient.extractMemories(
                            currentUserMessage,
                            context,
                            modelId
                    );
            if (extracted == null || extracted.isEmpty()) {
                return;
            }
            String normalizedUserText = normalizeEvidence(currentUserMessage);
            List<AiCookerClient.ExtractedMemoryCandidate> grounded = extracted
                    .stream()
                    .filter(candidate -> candidate != null
                            && candidate.sourceText() != null
                            && normalizedUserText.contains(normalizeEvidence(
                                    candidate.sourceText()
                            )))
                    .toList();
            userMemoryService.applyExtractedMemories(
                    userId,
                    conversationId,
                    grounded
            );
        } catch (Exception exception) {
            LOGGER.warn(
                    "user_memory_extraction_failed conversation={} error={}",
                    conversationId,
                    exception.getClass().getSimpleName()
            );
        }
    }

    private static String normalizeEvidence(String value) {
        String normalized = Normalizer.normalize(value, Normalizer.Form.NFKC)
                .toLowerCase(Locale.ROOT)
                .strip();
        return WHITESPACE.matcher(normalized).replaceAll(" ");
    }
}
