package com.aicooker.backend.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

import com.aicooker.backend.client.AiCookerClient;
import com.aicooker.backend.dto.UpdateMemoryRequest;
import com.aicooker.backend.entity.MemoryType;
import com.aicooker.backend.entity.UserEntity;
import com.aicooker.backend.entity.UserMemoryEntity;
import com.aicooker.backend.exception.MemoryNotFoundException;
import com.aicooker.backend.repository.UserMemoryRepository;
import com.aicooker.backend.repository.UserRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest
@ActiveProfiles("test")
@Transactional
class UserMemoryIntegrationTest {

    @Autowired
    private UserMemoryService memoryService;
    @Autowired
    private ConversationPersistenceService conversationPersistenceService;
    @Autowired
    private UserMemoryRepository memoryRepository;
    @Autowired
    private UserRepository userRepository;

    @Test
    void repeatedPreferenceIsDeduplicatedAndReinforced() {
        UserEntity user = createUser();
        UUID conversation = createConversation(user, "I prefer less oil.");

        memoryService.applyExtractedMemories(user.getId(), conversation, List.of(
                upsert(MemoryType.COOKING_PREFERENCE, "oil", "low", 0.90)
        ));
        memoryService.applyExtractedMemories(user.getId(), conversation, List.of(
                upsert(MemoryType.COOKING_PREFERENCE, "  OIL ", "low", 0.97)
        ));

        assertThat(memoryRepository.findByUser_IdAndActiveTrue(user.getId()))
                .hasSize(1)
                .first()
                .satisfies(memory -> {
                    assertThat(memory.getMemoryKey()).isEqualTo("oil");
                    assertThat(memory.getConfidence()).isEqualByComparingTo("0.9700");
                });
    }

    @Test
    void multilingualAndPluralFoodKeysAreCanonicalizedBeforeDeduplication() {
        UserEntity user = createUser();
        UUID conversation = createConversation(user, "我对花生过敏。");

        memoryService.applyExtractedMemories(user.getId(), conversation, List.of(
                upsert(MemoryType.DIETARY_RESTRICTION, "peanuts", "allergy", 0.94)
        ));
        memoryService.applyExtractedMemories(user.getId(), conversation, List.of(
                upsert(MemoryType.DIETARY_RESTRICTION, "花生", "allergy", 0.99)
        ));

        assertThat(memoryRepository.findByUser_IdAndActiveTrue(user.getId()))
                .hasSize(1)
                .first()
                .satisfies(memory -> {
                    assertThat(memory.getMemoryKey()).isEqualTo("peanut");
                    assertThat(memory.getConfidence()).isEqualByComparingTo("0.9900");
                });
    }

    @Test
    void legacyAliasRowsAreDeduplicatedAtTheReadBoundary() {
        UserEntity user = createUser();
        UUID conversation = createConversation(user, "我对花生过敏。");
        Instant now = Instant.now();
        memoryRepository.saveAll(List.of(
                new UserMemoryEntity(
                        UUID.randomUUID(),
                        user,
                        MemoryType.DIETARY_RESTRICTION,
                        "peanut",
                        "allergy",
                        new BigDecimal("0.9900"),
                        conversation,
                        now
                ),
                new UserMemoryEntity(
                        UUID.randomUUID(),
                        user,
                        MemoryType.DIETARY_RESTRICTION,
                        "peanuts",
                        "allergy",
                        new BigDecimal("0.9400"),
                        conversation,
                        now.minusSeconds(1)
                )
        ));

        assertThat(memoryService.list(user.getId()))
                .singleElement()
                .satisfies(memory -> {
                    assertThat(memory.key()).isEqualTo("peanut");
                    assertThat(memory.value()).isEqualTo("allergy");
                });
        assertThat(memoryService.contextForAgent(user.getId()))
                .containsExactly("Dietary restriction — peanut: allergy");
    }

    @Test
    void explicitContradictionReplacesCasualPreference() {
        UserEntity user = createUser();
        UUID firstConversation = createConversation(user, "I prefer mild food.");
        UUID secondConversation = createConversation(user, "I enjoy spicy food now.");
        memoryService.applyExtractedMemories(user.getId(), firstConversation, List.of(
                upsert(MemoryType.COOKING_PREFERENCE, "spice", "mild", 0.94)
        ));

        memoryService.applyExtractedMemories(user.getId(), secondConversation, List.of(
                upsert(MemoryType.COOKING_PREFERENCE, "spice", "very spicy", 0.96)
        ));

        assertThat(memoryService.list(user.getId())).singleElement()
                .satisfies(memory -> {
                    assertThat(memory.value()).isEqualTo("very spicy");
                    assertThat(memory.updatedAt()).isAfterOrEqualTo(memory.createdAt());
                });
    }

    @Test
    void ambiguousChangeCannotRemoveSafetySensitiveRestriction() {
        UserEntity user = createUser();
        UUID conversation = createConversation(user, "I have a peanut allergy.");
        memoryService.applyExtractedMemories(user.getId(), conversation, List.of(
                upsert(MemoryType.DIETARY_RESTRICTION, "peanut", "allergy", 0.99)
        ));

        memoryService.applyExtractedMemories(user.getId(), conversation, List.of(
                candidate(
                        AiCookerClient.MemoryAction.DELETE,
                        MemoryType.DIETARY_RESTRICTION,
                        "peanut",
                        "remove",
                        0.90
                )
        ));

        assertThat(memoryService.contextForAgent(user.getId()))
                .containsExactly("Dietary restriction — peanut: allergy");
    }

    @Test
    void memoryIsSharedAcrossConversationsButIsolatedByUserAndDeletion() {
        UserEntity alice = createUser();
        UserEntity bob = createUser();
        UUID conversationA = createConversation(alice, "I avoid coriander.");
        createConversation(alice, "Recommend dinner.");
        createConversation(bob, "Recommend dinner.");
        memoryService.applyExtractedMemories(alice.getId(), conversationA, List.of(
                upsert(MemoryType.DIETARY_RESTRICTION, "coriander", "avoid", 0.99)
        ));

        assertThat(memoryService.contextForAgent(alice.getId()))
                .containsExactly("Dietary restriction — coriander: avoid");
        assertThat(memoryService.contextForAgent(bob.getId())).isEmpty();

        UUID memoryId = memoryService.list(alice.getId()).getFirst().id();
        assertThatThrownBy(() -> memoryService.update(
                bob.getId(),
                memoryId,
                new UpdateMemoryRequest(
                        MemoryType.DIETARY_RESTRICTION,
                        "coriander",
                        "allow"
                )
        )).isInstanceOf(MemoryNotFoundException.class);

        memoryService.delete(alice.getId(), memoryId);
        assertThat(memoryService.contextForAgent(alice.getId())).isEmpty();
    }

    @Test
    void manualCorrectionIsVisibleWithoutExposingConfidence() {
        UserEntity user = createUser();
        UUID conversation = createConversation(user, "I cook for two.");
        memoryService.applyExtractedMemories(user.getId(), conversation, List.of(
                upsert(MemoryType.HOUSEHOLD_CONTEXT, "servings", "two", 0.91)
        ));
        UUID memoryId = memoryService.list(user.getId()).getFirst().id();

        var corrected = memoryService.update(
                user.getId(),
                memoryId,
                new UpdateMemoryRequest(
                        MemoryType.HOUSEHOLD_CONTEXT,
                        "usual servings",
                        "three"
                )
        );

        assertThat(corrected.key()).isEqualTo("usual servings");
        assertThat(corrected.value()).isEqualTo("three");
    }

    private UserEntity createUser() {
        Instant now = Instant.now();
        return userRepository.save(new UserEntity(
                UUID.randomUUID(),
                "memory-" + UUID.randomUUID(),
                "not-a-real-password-hash",
                now,
                now
        ));
    }

    private UUID createConversation(UserEntity user, String message) {
        UUID id = UUID.randomUUID();
        conversationPersistenceService.recordUserMessage(
                user.getId(), id, message, null
        );
        return id;
    }

    private static AiCookerClient.ExtractedMemoryCandidate upsert(
            MemoryType type,
            String key,
            String value,
            double confidence
    ) {
        return candidate(
                AiCookerClient.MemoryAction.UPSERT,
                type,
                key,
                value,
                confidence
        );
    }

    private static AiCookerClient.ExtractedMemoryCandidate candidate(
            AiCookerClient.MemoryAction action,
            MemoryType type,
            String key,
            String value,
            double confidence
    ) {
        return new AiCookerClient.ExtractedMemoryCandidate(
                action,
                type,
                key,
                value,
                confidence,
                "grounded user quote"
        );
    }
}
