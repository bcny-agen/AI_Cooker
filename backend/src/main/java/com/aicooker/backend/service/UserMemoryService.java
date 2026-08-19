package com.aicooker.backend.service;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Clock;
import java.time.Instant;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.UUID;
import java.util.regex.Pattern;

import com.aicooker.backend.client.AiCookerClient;
import com.aicooker.backend.dto.MemoryResponse;
import com.aicooker.backend.dto.UpdateMemoryRequest;
import com.aicooker.backend.entity.MemoryType;
import com.aicooker.backend.entity.UserMemoryEntity;
import com.aicooker.backend.exception.MemoryNotFoundException;
import com.aicooker.backend.exception.MemoryValidationException;
import com.aicooker.backend.repository.UserMemoryRepository;
import com.aicooker.backend.repository.UserRepository;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class UserMemoryService {

    private static final int AGENT_MEMORY_LIMIT = 24;
    private static final double MIN_AUTOMATIC_CONFIDENCE = 0.80;
    private static final double SAFETY_CHANGE_CONFIDENCE = 0.98;
    private static final Pattern WHITESPACE = Pattern.compile("\\s+");

    private final UserMemoryRepository memoryRepository;
    private final UserRepository userRepository;
    private final Clock clock;

    public UserMemoryService(
            UserMemoryRepository memoryRepository,
            UserRepository userRepository,
            Clock clock
    ) {
        this.memoryRepository = memoryRepository;
        this.userRepository = userRepository;
        this.clock = clock;
    }

    @Transactional(readOnly = true)
    public List<MemoryResponse> list(UUID userId) {
        return activeMemories(userId).stream()
                .map(UserMemoryService::toResponse)
                .toList();
    }

    @Transactional(readOnly = true)
    public List<String> contextForAgent(UUID userId) {
        return activeMemories(userId).stream()
                .limit(AGENT_MEMORY_LIMIT)
                .map(UserMemoryService::formatForAgent)
                .toList();
    }

    @Transactional
    public MemoryResponse update(
            UUID userId,
            UUID memoryId,
            UpdateMemoryRequest request
    ) {
        UserMemoryEntity memory = memoryRepository
                .findByIdAndUser_IdAndActiveTrue(memoryId, userId)
                .orElseThrow(() -> new MemoryNotFoundException(memoryId));
        String normalizedKey = normalizeKey(request.key());
        if (!memory.getMemoryKey().equals(normalizedKey)) {
            var collision = memoryRepository.findByUser_IdAndMemoryKey(
                    userId,
                    normalizedKey
            );
            if (collision.isPresent() && !collision.get().getId().equals(memoryId)) {
                throw new MemoryValidationException(
                        "A memory with this key exists."
                );
            }
        }
        memory.correct(
                request.memoryType(),
                normalizedKey,
                normalizeValue(request.value()),
                clock.instant()
        );
        return toResponse(memory);
    }

    @Transactional
    public void delete(UUID userId, UUID memoryId) {
        UserMemoryEntity memory = memoryRepository
                .findByIdAndUser_IdAndActiveTrue(memoryId, userId)
                .orElseThrow(() -> new MemoryNotFoundException(memoryId));
        memory.deactivate(clock.instant());
    }

    @Transactional
    public void applyExtractedMemories(
            UUID userId,
            UUID sourceConversationId,
            List<AiCookerClient.ExtractedMemoryCandidate> candidates
    ) {
        for (AiCookerClient.ExtractedMemoryCandidate candidate : candidates) {
            applyCandidate(userId, sourceConversationId, candidate);
        }
    }

    private void applyCandidate(
            UUID userId,
            UUID sourceConversationId,
            AiCookerClient.ExtractedMemoryCandidate candidate
    ) {
        if (candidate == null
                || candidate.confidence() < MIN_AUTOMATIC_CONFIDENCE) {
            return;
        }
        String key = normalizeKey(candidate.key());
        UserMemoryEntity existing = memoryRepository
                .findByUser_IdAndMemoryKey(userId, key)
                .orElse(null);

        if (candidate.action() == AiCookerClient.MemoryAction.DELETE) {
            if (existing == null || !existing.isActive()) {
                return;
            }
            if (isSafetySensitive(existing.getMemoryType())
                    && candidate.confidence() < SAFETY_CHANGE_CONFIDENCE) {
                return;
            }
            existing.deactivate(clock.instant());
            return;
        }

        String value = normalizeValue(candidate.value());
        BigDecimal confidence = BigDecimal.valueOf(candidate.confidence())
                .setScale(4, RoundingMode.HALF_UP);
        Instant now = clock.instant();
        if (existing == null) {
            var user = userRepository.findById(userId)
                    .orElseThrow(() -> new AccessDeniedException(
                            "Authenticated user no longer exists."
                    ));
            memoryRepository.save(new UserMemoryEntity(
                    UUID.randomUUID(),
                    user,
                    candidate.memoryType(),
                    key,
                    value,
                    confidence,
                    sourceConversationId,
                    now
            ));
            return;
        }

        boolean changesValue = !existing.getMemoryValue().equalsIgnoreCase(value)
                || existing.getMemoryType() != candidate.memoryType();
        if (changesValue
                && isSafetySensitive(existing.getMemoryType())
                && candidate.confidence() < SAFETY_CHANGE_CONFIDENCE) {
            return;
        }
        BigDecimal reinforcedConfidence = changesValue
                ? confidence
                : existing.getConfidence().max(confidence);
        MemoryType resolvedType = isSafetySensitive(existing.getMemoryType())
                && !isSafetySensitive(candidate.memoryType())
                ? existing.getMemoryType()
                : candidate.memoryType();
        existing.reinforceOrReplace(
                resolvedType,
                changesValue ? value : existing.getMemoryValue(),
                reinforcedConfidence,
                sourceConversationId,
                now
        );
    }

    private List<UserMemoryEntity> activeMemories(UUID userId) {
        return memoryRepository.findByUser_IdAndActiveTrue(userId).stream()
                .sorted(Comparator
                        .comparingInt((UserMemoryEntity item) -> priority(
                                item.getMemoryType()
                        ))
                        .thenComparing(UserMemoryEntity::getMemoryKey))
                .toList();
    }

    private static int priority(MemoryType type) {
        return switch (type) {
            case DIETARY_RESTRICTION -> 0;
            case NUTRITION_GOAL -> 1;
            case FOOD_PREFERENCE -> 2;
            case CUISINE_PREFERENCE -> 3;
            case COOKING_PREFERENCE -> 4;
            case HOUSEHOLD_CONTEXT -> 5;
        };
    }

    private static boolean isSafetySensitive(MemoryType type) {
        return type == MemoryType.DIETARY_RESTRICTION;
    }

    private static String normalizeKey(String value) {
        if (value == null) {
            throw new MemoryValidationException("Memory key is required.");
        }
        String normalized = WHITESPACE.matcher(value.strip().toLowerCase(Locale.ROOT))
                .replaceAll(" ");
        if (normalized.isBlank() || normalized.length() > 80) {
            throw new MemoryValidationException("Memory key is invalid.");
        }
        return normalized;
    }

    private static String normalizeValue(String value) {
        if (value == null) {
            throw new MemoryValidationException("Memory value is required.");
        }
        String normalized = WHITESPACE.matcher(value.strip()).replaceAll(" ");
        if (normalized.isBlank() || normalized.length() > 255) {
            throw new MemoryValidationException("Memory value is invalid.");
        }
        return normalized;
    }

    private static String formatForAgent(UserMemoryEntity memory) {
        String category = switch (memory.getMemoryType()) {
            case DIETARY_RESTRICTION -> "Dietary restriction";
            case FOOD_PREFERENCE -> "Food preference";
            case CUISINE_PREFERENCE -> "Cuisine preference";
            case COOKING_PREFERENCE -> "Cooking preference";
            case HOUSEHOLD_CONTEXT -> "Cooking habit";
            case NUTRITION_GOAL -> "Nutrition goal";
        };
        return category + " — " + memory.getMemoryKey() + ": "
                + memory.getMemoryValue();
    }

    private static MemoryResponse toResponse(UserMemoryEntity memory) {
        return new MemoryResponse(
                memory.getId(),
                memory.getMemoryType(),
                memory.getMemoryKey(),
                memory.getMemoryValue(),
                memory.getCreatedAt(),
                memory.getUpdatedAt()
        );
    }
}
