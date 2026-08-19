package com.aicooker.backend.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.UUID;

import com.aicooker.backend.AiCookerBackendApplication;
import com.aicooker.backend.entity.MessageRole;
import com.aicooker.backend.entity.ModelId;
import com.aicooker.backend.entity.UserEntity;
import com.aicooker.backend.entity.UploadedImageEntity;
import com.aicooker.backend.entity.ForumPostEntity;
import com.aicooker.backend.exception.ConversationNotFoundException;
import com.aicooker.backend.repository.ConversationRepository;
import com.aicooker.backend.repository.ForumPostRepository;
import com.aicooker.backend.repository.GeneratedImageRepository;
import com.aicooker.backend.repository.MessageRepository;
import com.aicooker.backend.repository.UserRepository;
import com.aicooker.backend.repository.UploadedImageRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.test.context.ActiveProfiles;
import jakarta.persistence.EntityManager;

@SpringBootTest(classes = AiCookerBackendApplication.class)
@ActiveProfiles("test")
@Import(ConversationPersistenceIntegrationTest.TestClockConfig.class)
class ConversationPersistenceIntegrationTest {

    private static final Instant INITIAL_TIME =
            Instant.parse("2026-08-07T12:00:00Z");
    private static final UUID USER_ID =
            UUID.fromString("0f0c2f0d-a51b-44f6-915b-ed9d3f583804");

    @Autowired
    private ConversationPersistenceService persistenceService;

    @Autowired
    private ConversationQueryService queryService;

    @Autowired
    private ConversationManagementPersistenceService managementPersistence;

    @Autowired
    private ConversationRepository conversationRepository;

    @Autowired
    private ForumPostRepository forumPostRepository;

    @Autowired
    private GeneratedImageRepository generatedImageRepository;

    @Autowired
    private MessageRepository messageRepository;

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private UploadedImageRepository imageRepository;

    @Autowired
    private MutableClock clock;

    @Autowired
    private EntityManager entityManager;

    @BeforeEach
    void cleanDatabase() {
        forumPostRepository.deleteAllInBatch();
        generatedImageRepository.deleteAllInBatch();
        messageRepository.deleteAllInBatch();
        conversationRepository.deleteAllInBatch();
        imageRepository.deleteAllInBatch();
        userRepository.deleteAllInBatch();
        clock.set(INITIAL_TIME);
        userRepository.save(new UserEntity(
                USER_ID,
                "alice",
                "test-hash",
                INITIAL_TIME,
                INITIAL_TIME
        ));
    }

    @Test
    void createsConversationTitleAndPersistsUserMessage() {
        UUID conversationId = UUID.randomUUID();
        UUID imageId = UUID.randomUUID();
        UserEntity owner = userRepository.findById(USER_ID).orElseThrow();
        imageRepository.save(new UploadedImageEntity(
                imageId,
                owner,
                "users/%s/images/test.jpg".formatted(USER_ID),
                "ingredients.jpg",
                "image/jpeg",
                123L,
                INITIAL_TIME
        ));

        persistenceService.recordUserMessage(
                USER_ID,
                conversationId,
                "  Tomato   eggs recipe  ",
                imageId
        );

        var conversation = queryService.getConversation(USER_ID, conversationId);
        var messages = queryService.listMessages(USER_ID, conversationId, 0, 10);

        assertThat(conversation.title()).isEqualTo("Tomato eggs recipe");
        assertThat(conversation.modelId()).isEqualTo(ModelId.STEP_FLASH_3_7);
        assertThat(conversation.createdAt()).isEqualTo(INITIAL_TIME);
        assertThat(messages.totalElements()).isEqualTo(1);
        assertThat(messages.content().getFirst().role()).isEqualTo(MessageRole.USER);
        assertThat(messages.content().getFirst().content())
                .isEqualTo("  Tomato   eggs recipe  ");
        assertThat(messages.content().getFirst().imageId()).isEqualTo(imageId);
    }

    @Test
    void persistsSelectedModelAndExplicitSwitch() {
        UUID conversationId = UUID.randomUUID();
        persistenceService.recordUserMessage(
                USER_ID,
                conversationId,
                "tofu recipe",
                null,
                ModelId.DEEPSEEK_V4_PRO
        );

        assertThat(queryService.getConversation(USER_ID, conversationId).modelId())
                .isEqualTo(ModelId.DEEPSEEK_V4_PRO);

        persistenceService.changeModel(
                USER_ID,
                conversationId,
                ModelId.STEP_FLASH_3_7
        );
        assertThat(queryService.getConversation(USER_ID, conversationId).modelId())
                .isEqualTo(ModelId.STEP_FLASH_3_7);
    }

    @Test
    void continuesExistingConversationAndPersistsAssistantMessage() {
        UUID conversationId = UUID.randomUUID();
        persistenceService.recordUserMessage(USER_ID, conversationId, "first", null);

        Instant assistantTime = INITIAL_TIME.plusSeconds(5);
        clock.set(assistantTime);
        persistenceService.recordAssistantMessage(USER_ID, conversationId, "answer");

        Instant continuationTime = INITIAL_TIME.plusSeconds(10);
        clock.set(continuationTime);
        persistenceService.recordUserMessage(
                USER_ID,
                conversationId,
                "follow up",
                null
        );

        var messages = queryService.listMessages(USER_ID, conversationId, 0, 10);

        assertThat(conversationRepository.count()).isEqualTo(1);
        assertThat(messages.content())
                .extracting(message -> message.role())
                .containsExactly(
                        MessageRole.USER,
                        MessageRole.ASSISTANT,
                        MessageRole.USER
                );
        assertThat(messages.content().get(1).content()).isEqualTo("answer");
        assertThat(messages.content().get(1).imageId()).isNull();
        assertThat(queryService.getConversation(USER_ID, conversationId).updatedAt())
                .isEqualTo(continuationTime);
    }

    @Test
    void listsMostRecentlyUpdatedConversationFirst() {
        UUID firstConversation = UUID.randomUUID();
        UUID secondConversation = UUID.randomUUID();

        persistenceService.recordUserMessage(USER_ID, firstConversation, "first", null);
        clock.set(INITIAL_TIME.plusSeconds(5));
        persistenceService.recordUserMessage(USER_ID, secondConversation, "second", null);
        clock.set(INITIAL_TIME.plusSeconds(10));
        persistenceService.recordUserMessage(USER_ID, firstConversation, "recent", null);

        var conversations = queryService.listConversations(USER_ID, 0, 10);

        assertThat(conversations.content())
                .extracting(conversation -> conversation.id())
                .containsExactly(firstConversation, secondConversation);
    }

    @Test
    void returnsDeterministicMessagePages() {
        UUID conversationId = UUID.randomUUID();
        persistenceService.recordUserMessage(USER_ID, conversationId, "one", null);
        persistenceService.recordAssistantMessage(USER_ID, conversationId, "two");
        persistenceService.recordUserMessage(USER_ID, conversationId, "three", null);
        persistenceService.recordAssistantMessage(USER_ID, conversationId, "four");

        var firstPage = queryService.listMessages(USER_ID, conversationId, 0, 2);
        var secondPage = queryService.listMessages(USER_ID, conversationId, 1, 2);

        assertThat(firstPage.content())
                .extracting(message -> message.content())
                .containsExactly("one", "two");
        assertThat(secondPage.content())
                .extracting(message -> message.content())
                .containsExactly("three", "four");
        assertThat(firstPage.totalElements()).isEqualTo(4);
        assertThat(firstPage.totalPages()).isEqualTo(2);
    }

    @Test
    void hidesConversationFromAnotherUser() {
        UUID conversationId = UUID.randomUUID();
        UUID otherUserId = UUID.randomUUID();
        userRepository.save(new UserEntity(
                otherUserId,
                "bob",
                "test-hash",
                INITIAL_TIME,
                INITIAL_TIME
        ));
        persistenceService.recordUserMessage(
                USER_ID,
                conversationId,
                "private recipe",
                null
        );

        assertThatThrownBy(() -> queryService.getConversation(
                otherUserId,
                conversationId
        )).isInstanceOf(ConversationNotFoundException.class);
        assertThatThrownBy(() -> queryService.listMessages(
                otherUserId,
                conversationId,
                0,
                10
        )).isInstanceOf(ConversationNotFoundException.class);
        assertThatThrownBy(() -> persistenceService.recordUserMessage(
                otherUserId,
                conversationId,
                "attempted access",
                null
        )).isInstanceOf(ConversationNotFoundException.class);
    }

    @Test
    void recoveryHistoryIsOwnedOrderedAndExcludesCurrentMessage() {
        UUID conversationId = UUID.randomUUID();
        UUID otherUserId = UUID.randomUUID();
        userRepository.save(new UserEntity(
                otherUserId,
                "bob",
                "test-hash",
                INITIAL_TIME,
                INITIAL_TIME
        ));
        persistenceService.recordUserMessage(
                USER_ID, conversationId, "earlier question", null
        );
        persistenceService.recordAssistantMessage(
                USER_ID, conversationId, "earlier answer"
        );
        var current = persistenceService.recordUserMessage(
                USER_ID, conversationId, "current follow-up", null
        );

        var history = persistenceService.recoveryHistory(
                USER_ID,
                conversationId,
                current.messageId()
        );

        assertThat(history).extracting(
                ConversationPersistenceService.RecoveryHistoryMessage::content
        ).containsExactly("earlier question", "earlier answer");
        assertThatThrownBy(() -> persistenceService.recoveryHistory(
                otherUserId,
                conversationId,
                current.messageId()
        )).isInstanceOf(ConversationNotFoundException.class);
    }

    @Test
    void renamePreservesConversationIdMessagesAndAgentIndependence() {
        UUID conversationId = UUID.randomUUID();
        persistenceService.recordUserMessage(
                USER_ID, conversationId, "first message", null
        );
        persistenceService.recordAssistantMessage(
                USER_ID, conversationId, "first answer"
        );
        var messageIdsBefore = messageRepository
                .findByConversation_IdOrderByCreatedAtAscIdAsc(conversationId)
                .stream()
                .map(message -> message.getId())
                .toList();

        var renamed = managementPersistence.rename(
                USER_ID,
                conversationId,
                "  Weeknight tomato dinner  "
        );

        assertThat(renamed.id()).isEqualTo(conversationId);
        assertThat(renamed.title()).isEqualTo("Weeknight tomato dinner");
        assertThat(messageRepository
                .findByConversation_IdOrderByCreatedAtAscIdAsc(conversationId)
                .stream()
                .map(message -> message.getId())
                .toList()).isEqualTo(messageIdsBefore);
    }

    @Test
    void businessDeletionHandlesRichLegacyHistoryAndKeepsForumPostAndImage() {
        UUID conversationId = UUID.randomUUID();
        UserEntity owner = userRepository.findById(USER_ID).orElseThrow();
        UUID imageId = UUID.randomUUID();
        imageRepository.save(new UploadedImageEntity(
                imageId,
                owner,
                "users/%s/images/keep.jpg".formatted(USER_ID),
                "ingredients.jpg",
                "image/jpeg",
                123L,
                INITIAL_TIME
        ));
        persistenceService.recordUserMessage(
                USER_ID,
                conversationId,
                "private ingredients",
                imageId
        );
        persistenceService.recordAssistantMessage(
                USER_ID,
                conversationId,
                "first assistant recipe"
        );
        persistenceService.recordUserMessage(
                USER_ID,
                conversationId,
                "legacy follow-up",
                null
        );
        persistenceService.recordAssistantMessage(
                USER_ID,
                conversationId,
                "second assistant recipe"
        );
        var conversation = conversationRepository.findById(conversationId)
                .orElseThrow();
        UUID forumPostId = UUID.randomUUID();
        forumPostRepository.saveAndFlush(new ForumPostEntity(
                forumPostId,
                owner,
                "Public recipe",
                "Only published content remains.",
                imageRepository.findById(imageId).orElseThrow(),
                conversation,
                INITIAL_TIME,
                INITIAL_TIME
        ));

        managementPersistence.deleteBusinessConversation(
                USER_ID,
                conversationId
        );
        entityManager.clear();

        assertThat(conversationRepository.findById(conversationId)).isEmpty();
        assertThat(messageRepository.findByConversation_Id(
                conversationId,
                org.springframework.data.domain.Pageable.unpaged()
        ).getContent()).isEmpty();
        assertThat(imageRepository.findById(imageId)).isPresent();
        var remainingPost = forumPostRepository.findById(forumPostId)
                .orElseThrow();
        assertThat(remainingPost.getSourceConversation()).isNull();
        assertThat(remainingPost.getImage().getId()).isEqualTo(imageId);
        assertThat(remainingPost.getContent())
                .isEqualTo("Only published content remains.");
    }

    @Test
    void anotherUserCannotRenameOrDeleteBusinessConversation() {
        UUID conversationId = UUID.randomUUID();
        UUID otherUserId = UUID.randomUUID();
        userRepository.save(new UserEntity(
                otherUserId,
                "bob-management",
                "test-hash",
                INITIAL_TIME,
                INITIAL_TIME
        ));
        persistenceService.recordUserMessage(
                USER_ID, conversationId, "private", null
        );

        assertThatThrownBy(() -> managementPersistence.rename(
                otherUserId, conversationId, "stolen"
        )).isInstanceOf(ConversationNotFoundException.class);
        assertThatThrownBy(() -> managementPersistence.deleteBusinessConversation(
                otherUserId, conversationId
        )).isInstanceOf(ConversationNotFoundException.class);
        assertThat(conversationRepository.findById(conversationId)).isPresent();
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class TestClockConfig {

        @Bean
        @Primary
        MutableClock mutableClock() {
            return new MutableClock(INITIAL_TIME);
        }
    }

    static final class MutableClock extends Clock {

        private Instant current;

        private MutableClock(Instant current) {
            this.current = current;
        }

        void set(Instant current) {
            this.current = current;
        }

        @Override
        public ZoneId getZone() {
            return ZoneOffset.UTC;
        }

        @Override
        public Clock withZone(ZoneId zone) {
            if (!ZoneOffset.UTC.equals(zone)) {
                throw new IllegalArgumentException("Only UTC is supported in this test clock.");
            }
            return this;
        }

        @Override
        public Instant instant() {
            return current;
        }
    }
}
