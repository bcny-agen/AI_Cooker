package com.aicooker.backend.service;

import java.util.List;
import java.util.UUID;

import com.aicooker.backend.client.AiCookerClient;
import com.aicooker.backend.dto.ForumDraftResponse;
import com.aicooker.backend.entity.MessageEntity;
import com.aicooker.backend.entity.MessageRole;
import com.aicooker.backend.entity.ForumImageType;
import com.aicooker.backend.exception.ConversationNotFoundException;
import com.aicooker.backend.exception.InsufficientConversationException;
import com.aicooker.backend.repository.ConversationRepository;
import com.aicooker.backend.repository.MessageRepository;
import com.aicooker.backend.repository.GeneratedImageRepository;
import com.aicooker.backend.repository.UploadedImageRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ForumDraftService {

    private final ConversationRepository conversationRepository;
    private final MessageRepository messageRepository;
    private final UploadedImageRepository imageRepository;
    private final GeneratedImageRepository generatedImageRepository;
    private final AiCookerClient aiCookerClient;

    public ForumDraftService(
            ConversationRepository conversationRepository,
            MessageRepository messageRepository,
            UploadedImageRepository imageRepository,
            GeneratedImageRepository generatedImageRepository,
            AiCookerClient aiCookerClient
    ) {
        this.conversationRepository = conversationRepository;
        this.messageRepository = messageRepository;
        this.imageRepository = imageRepository;
        this.generatedImageRepository = generatedImageRepository;
        this.aiCookerClient = aiCookerClient;
    }

    @Transactional(readOnly = true)
    public ForumDraftResponse generate(UUID userId, UUID conversationId) {
        var conversation = conversationRepository
                .findByIdAndUser_Id(conversationId, userId)
                .orElseThrow(() -> new ConversationNotFoundException(
                        conversationId
                ));
        List<MessageEntity> visibleMessages = messageRepository
                .findByConversation_IdOrderByCreatedAtAscIdAsc(conversationId)
                .stream()
                .filter(message -> message.getRole() == MessageRole.USER
                        || message.getRole() == MessageRole.ASSISTANT)
                .filter(message -> !message.getContent().isBlank())
                .toList();
        boolean hasUser = visibleMessages.stream()
                .anyMatch(message -> message.getRole() == MessageRole.USER);
        boolean hasAssistant = visibleMessages.stream()
                .anyMatch(message -> message.getRole() == MessageRole.ASSISTANT);
        if (!hasUser || !hasAssistant) {
            throw new InsufficientConversationException();
        }

        List<AiCookerClient.DraftMessage> history = visibleMessages.stream()
                .map(message -> new AiCookerClient.DraftMessage(
                        message.getRole().name(),
                        message.getContent()
                ))
                .toList();
        AiCookerClient.ForumDraftResult generated =
                aiCookerClient.generateForumDraft(
                        conversationId,
                        history,
                        conversation.getSelectedModel()
                );

        SuggestedImage suggestedImage = suggestedImage(
                visibleMessages,
                userId,
                conversationId
        );
        return new ForumDraftResponse(
                conversationId,
                generated.title(),
                generated.content(),
                generated.dishName(),
                suggestedImage.id(),
                suggestedImage.type(),
                conversation.getSelectedModel()
        );
    }

    private SuggestedImage suggestedImage(
            List<MessageEntity> messages,
            UUID userId,
            UUID conversationId
    ) {
        var generated = generatedImageRepository
                .findFirstByConversation_IdAndUser_IdOrderByCreatedAtDescIdDesc(
                        conversationId,
                        userId
                );
        if (generated.isPresent()) {
            return new SuggestedImage(
                    generated.get().getId(),
                    ForumImageType.AI_GENERATED
            );
        }
        for (int index = messages.size() - 1; index >= 0; index--) {
            var image = messages.get(index).getImage();
            if (image != null && imageRepository
                    .findByIdAndUser_Id(image.getId(), userId)
                    .isPresent()) {
                return new SuggestedImage(
                        image.getId(),
                        ForumImageType.USER_UPLOAD
                );
            }
        }
        return new SuggestedImage(null, null);
    }

    private record SuggestedImage(UUID id, ForumImageType type) {
    }
}
