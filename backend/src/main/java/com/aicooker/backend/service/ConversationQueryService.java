package com.aicooker.backend.service;

import java.util.UUID;

import com.aicooker.backend.dto.ConversationResponse;
import com.aicooker.backend.dto.MessageResponse;
import com.aicooker.backend.dto.PageResponse;
import com.aicooker.backend.entity.ConversationEntity;
import com.aicooker.backend.entity.MessageEntity;
import com.aicooker.backend.exception.ConversationNotFoundException;
import com.aicooker.backend.repository.ConversationRepository;
import com.aicooker.backend.repository.MessageRepository;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ConversationQueryService {

    private static final Sort CONVERSATION_ORDER = Sort.by(
            Sort.Order.desc("updatedAt"),
            Sort.Order.desc("id")
    );
    private static final Sort MESSAGE_ORDER = Sort.by(
            Sort.Order.asc("createdAt"),
            Sort.Order.asc("id")
    );

    private final ConversationRepository conversationRepository;
    private final MessageRepository messageRepository;
    private final GeneratedImageService generatedImageService;

    public ConversationQueryService(
            ConversationRepository conversationRepository,
            MessageRepository messageRepository,
            GeneratedImageService generatedImageService
    ) {
        this.conversationRepository = conversationRepository;
        this.messageRepository = messageRepository;
        this.generatedImageService = generatedImageService;
    }

    @Transactional(readOnly = true)
    public PageResponse<ConversationResponse> listConversations(
            UUID userId,
            int page,
            int size
    ) {
        return PageResponse.from(conversationRepository
                .findByUser_Id(userId, PageRequest.of(page, size, CONVERSATION_ORDER))
                .map(ConversationQueryService::toConversationResponse));
    }

    @Transactional(readOnly = true)
    public ConversationResponse getConversation(
            UUID userId,
            UUID conversationId
    ) {
        return conversationRepository.findByIdAndUser_Id(conversationId, userId)
                .map(ConversationQueryService::toConversationResponse)
                .orElseThrow(() -> new ConversationNotFoundException(conversationId));
    }

    @Transactional(readOnly = true)
    public PageResponse<MessageResponse> listMessages(
            UUID userId,
            UUID conversationId,
            int page,
            int size
    ) {
        conversationRepository.findByIdAndUser_Id(conversationId, userId)
                .orElseThrow(() -> new ConversationNotFoundException(conversationId));

        var messages = messageRepository
                .findByConversation_Id(
                        conversationId,
                        PageRequest.of(page, size, MESSAGE_ORDER)
                );
        var generatedImages = generatedImageService.forMessages(
                userId,
                messages.getContent().stream().map(MessageEntity::getId).toList()
        );
        return PageResponse.from(messages.map(message -> toMessageResponse(
                message,
                generatedImages.getOrDefault(message.getId(), java.util.List.of())
        )));
    }

    private static ConversationResponse toConversationResponse(
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

    private static MessageResponse toMessageResponse(
            MessageEntity message,
            java.util.List<com.aicooker.backend.dto.GeneratedImageResponse> generatedImages
    ) {
        return new MessageResponse(
                message.getId(),
                message.getRole(),
                message.getContent(),
                message.getImage() == null ? null : message.getImage().getId(),
                message.getCreatedAt(),
                generatedImages
        );
    }
}
