package com.aicooker.backend.service;

import java.time.Clock;
import java.util.UUID;

import com.aicooker.backend.dto.ConversationResponse;
import com.aicooker.backend.entity.ConversationEntity;
import com.aicooker.backend.exception.BusinessStorageOperationException;
import com.aicooker.backend.exception.ConversationNotFoundException;
import com.aicooker.backend.exception.DatabaseFailureDiagnostics;
import com.aicooker.backend.repository.ConversationRepository;
import com.aicooker.backend.repository.ForumPostRepository;
import com.aicooker.backend.repository.MessageRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ConversationManagementPersistenceService {

    private static final Logger LOGGER = LoggerFactory.getLogger(
            ConversationManagementPersistenceService.class
    );

    private final ConversationRepository conversationRepository;
    private final ForumPostRepository forumPostRepository;
    private final MessageRepository messageRepository;
    private final Clock clock;

    public ConversationManagementPersistenceService(
            ConversationRepository conversationRepository,
            ForumPostRepository forumPostRepository,
            MessageRepository messageRepository,
            Clock clock
    ) {
        this.conversationRepository = conversationRepository;
        this.forumPostRepository = forumPostRepository;
        this.messageRepository = messageRepository;
        this.clock = clock;
    }

    @Transactional(readOnly = true)
    public void requireOwnership(UUID userId, UUID conversationId) {
        ownedConversation(userId, conversationId);
    }

    @Transactional
    public ConversationResponse rename(
            UUID userId,
            UUID conversationId,
            String requestedTitle
    ) {
        ConversationEntity conversation = ownedConversation(
                userId,
                conversationId
        );
        String title = requestedTitle.strip();
        conversation.rename(title, clock.instant());
        return toResponse(conversation);
    }

    @Transactional
    public void deleteBusinessConversation(
            UUID userId,
            UUID conversationId
    ) {
        String operation = "LOAD_OWNED_CONVERSATION";
        try {
            ConversationEntity conversation = ownedConversation(
                    userId,
                    conversationId
            );
            long messageRows = messageRepository.countByConversation_Id(
                    conversationId
            );
            operation = "CLEAR_FORUM_SOURCE";
            int forumRows = forumPostRepository.clearSourceConversation(
                    conversationId.toString()
            );
            LOGGER.info(
                    "conversation_delete operation={} conversationId={} rows={}",
                    operation,
                    conversationId,
                    forumRows
            );
            operation = "DELETE_BUSINESS_CONVERSATION";
            conversationRepository.delete(conversation);
            conversationRepository.flush();
            LOGGER.info(
                    "conversation_delete operation={} conversationId={} "
                            + "conversationRows=1 messageCascadeRows={}",
                    operation,
                    conversationId,
                    messageRows
            );
        } catch (DataAccessException exception) {
            logDatabaseFailure(operation, conversationId, exception);
            throw new BusinessStorageOperationException(
                    operation,
                    exception
            );
        }
    }

    private ConversationEntity ownedConversation(
            UUID userId,
            UUID conversationId
    ) {
        return conversationRepository.findByIdAndUser_Id(conversationId, userId)
                .orElseThrow(() -> new ConversationNotFoundException(
                        conversationId
                ));
    }

    private static ConversationResponse toResponse(
            ConversationEntity conversation
    ) {
        return new ConversationResponse(
                conversation.getId(),
                conversation.getTitle(),
                conversation.getSelectedModel(),
                conversation.getCreatedAt(),
                conversation.getUpdatedAt()
        );
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
}
