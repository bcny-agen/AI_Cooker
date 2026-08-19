package com.aicooker.backend.service;

import java.time.Clock;
import java.time.Instant;
import java.util.UUID;

import com.aicooker.backend.entity.ConversationEntity;
import com.aicooker.backend.entity.MessageEntity;
import com.aicooker.backend.entity.MessageRole;
import com.aicooker.backend.entity.ModelId;
import com.aicooker.backend.entity.UserEntity;
import com.aicooker.backend.entity.UploadedImageEntity;
import com.aicooker.backend.exception.ConversationNotFoundException;
import com.aicooker.backend.exception.ImageNotFoundException;
import com.aicooker.backend.exception.ConversationModelConflictException;
import com.aicooker.backend.exception.DatabaseFailureDiagnostics;
import com.aicooker.backend.repository.ConversationRepository;
import com.aicooker.backend.repository.MessageRepository;
import com.aicooker.backend.repository.UserRepository;
import com.aicooker.backend.repository.UploadedImageRepository;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.dao.DataAccessException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ConversationPersistenceService {

    public static final ModelId DEFAULT_MODEL = ModelId.STEP_FLASH_3_7;
    private static final Logger LOGGER = LoggerFactory.getLogger(
            ConversationPersistenceService.class
    );

    private final ConversationRepository conversationRepository;
    private final MessageRepository messageRepository;
    private final UserRepository userRepository;
    private final UploadedImageRepository imageRepository;
    private final ConversationTitleGenerator titleGenerator;
    private final Clock clock;

    public ConversationPersistenceService(
            ConversationRepository conversationRepository,
            MessageRepository messageRepository,
            UserRepository userRepository,
            UploadedImageRepository imageRepository,
            ConversationTitleGenerator titleGenerator,
            Clock clock
    ) {
        this.conversationRepository = conversationRepository;
        this.messageRepository = messageRepository;
        this.userRepository = userRepository;
        this.imageRepository = imageRepository;
        this.titleGenerator = titleGenerator;
        this.clock = clock;
    }

    @Transactional
    public RecordedUserMessage recordUserMessage(
            UUID userId,
            UUID conversationId,
            String content,
            UUID imageId,
            ModelId selectedModel
    ) {
        try {
            Instant now = clock.instant();
            ConversationEntity conversation = conversationRepository
                    .findById(conversationId)
                    .map(existing -> requireOwner(existing, userId))
                    .orElseGet(() -> createConversation(
                            userId,
                            conversationId,
                            content,
                            selectedModel,
                            now
                    ));

            if (conversation.getSelectedModel() != selectedModel) {
                throw new ConversationModelConflictException();
            }

            UploadedImageEntity image = imageId == null
                    ? null
                    : imageRepository.findByIdAndUser_Id(imageId, userId)
                    .orElseThrow(() -> new ImageNotFoundException(imageId));

            MessageEntity savedMessage = messageRepository.save(
                    new MessageEntity(
                            conversation,
                            MessageRole.USER,
                            content,
                            image,
                            now
                    )
            );
            conversation.touch(now);
            messageRepository.flush();
            return new RecordedUserMessage(savedMessage.getId());
        } catch (DataAccessException exception) {
            logDatabaseFailure(
                    "record_user_message",
                    conversationId,
                    exception
            );
            throw exception;
        }
    }

    @Transactional
    public RecordedUserMessage recordUserMessage(
            UUID userId,
            UUID conversationId,
            String content,
            UUID imageId
    ) {
        return recordUserMessage(
                userId,
                conversationId,
                content,
                imageId,
                DEFAULT_MODEL
        );
    }

    @Transactional(readOnly = true)
    public ModelId resolveModelForChat(
            UUID userId,
            UUID conversationId,
            ModelId requestedModel
    ) {
        return resolveChatContext(userId, conversationId, requestedModel).modelId();
    }

    @Transactional(readOnly = true)
    public ChatContext resolveChatContext(
            UUID userId,
            UUID conversationId,
            ModelId requestedModel
    ) {
        try {
            return conversationRepository.findById(conversationId)
                    .map(existing -> {
                        ConversationEntity owned = requireOwner(existing, userId);
                        if (requestedModel != null
                                && requestedModel != owned.getSelectedModel()) {
                            throw new ConversationModelConflictException();
                        }
                        return new ChatContext(owned.getSelectedModel(), true);
                    })
                    .orElseGet(() -> new ChatContext(
                            requestedModel == null
                                    ? DEFAULT_MODEL : requestedModel,
                            false
                    ));
        } catch (DataAccessException exception) {
            logDatabaseFailure(
                    "resolve_chat_context",
                    conversationId,
                    exception
            );
            throw exception;
        }
    }

    @Transactional(readOnly = true)
    public java.util.List<RecoveryHistoryMessage> recoveryHistory(
            UUID userId,
            UUID conversationId,
            Long beforeMessageId
    ) {
        try {
            conversationRepository.findByIdAndUser_Id(conversationId, userId)
                    .orElseThrow(() -> new ConversationNotFoundException(
                            conversationId
                    ));
            return messageRepository
                    .findByConversation_IdAndIdLessThanOrderByCreatedAtAscIdAsc(
                            conversationId,
                            beforeMessageId
                    )
                    .stream()
                    .map(message -> new RecoveryHistoryMessage(
                            message.getId(),
                            message.getRole(),
                            message.getContent()
                    ))
                    .toList();
        } catch (DataAccessException exception) {
            logDatabaseFailure(
                    "load_recovery_history",
                    conversationId,
                    exception
            );
            throw exception;
        }
    }

    @Transactional
    public void changeModel(
            UUID userId,
            UUID conversationId,
            ModelId modelId
    ) {
        ConversationEntity conversation = conversationRepository
                .findByIdAndUser_Id(conversationId, userId)
                .orElseThrow(() -> new ConversationNotFoundException(conversationId));
        conversation.changeModel(modelId, clock.instant());
    }

    @Transactional
    public RecordedAssistantMessage recordAssistantMessage(
            UUID userId,
            UUID conversationId,
            String content
    ) {
        try {
            Instant now = clock.instant();
            ConversationEntity conversation = conversationRepository
                    .findByIdAndUser_Id(conversationId, userId)
                    .orElseThrow(() -> new ConversationNotFoundException(
                            conversationId
                    ));

            MessageEntity savedMessage = messageRepository.save(new MessageEntity(
                    conversation,
                    MessageRole.ASSISTANT,
                    content,
                    null,
                    now
            ));
            conversation.touch(now);
            messageRepository.flush();
            return new RecordedAssistantMessage(savedMessage.getId());
        } catch (DataAccessException exception) {
            logDatabaseFailure(
                    "record_assistant_message",
                    conversationId,
                    exception
            );
            throw exception;
        }
    }

    private ConversationEntity createConversation(
            UUID userId,
            UUID conversationId,
            String firstMessage,
            ModelId selectedModel,
            Instant now
    ) {
        UserEntity owner = userRepository.findById(userId)
                .orElseThrow(() -> new AccessDeniedException(
                        "Authenticated user no longer exists."
                ));
        return conversationRepository.save(new ConversationEntity(
                conversationId,
                owner,
                titleGenerator.generate(firstMessage),
                selectedModel,
                now,
                now
        ));
    }

    private static ConversationEntity requireOwner(
            ConversationEntity conversation,
            UUID userId
    ) {
        if (!conversation.getUser().getId().equals(userId)) {
            throw new ConversationNotFoundException(conversation.getId());
        }
        return conversation;
    }

    private static void logDatabaseFailure(
            String operation,
            UUID conversationId,
            DataAccessException exception
    ) {
        DatabaseFailureDiagnostics details =
                DatabaseFailureDiagnostics.inspect(exception);
        LOGGER.error(
                "business_storage_failure operation={} conversationId={} "
                        + "exception={} rootCause={} sqlState={} vendorCode={}",
                operation,
                conversationId,
                details.exceptionClass(),
                details.rootCauseClass(),
                details.sqlState(),
                details.vendorCode()
        );
    }

    public record ChatContext(ModelId modelId, boolean existingConversation) {
    }

    public record RecordedUserMessage(Long messageId) {
    }

    public record RecordedAssistantMessage(Long messageId) {
    }

    public record RecoveryHistoryMessage(
            Long messageId,
            MessageRole role,
            String content
    ) {
    }
}
