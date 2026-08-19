package com.aicooker.backend.entity;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

@Entity
@Table(name = "generated_images")
public class GeneratedImageEntity {

    @Id
    @JdbcTypeCode(SqlTypes.CHAR)
    @Column(nullable = false, updatable = false, length = 36)
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false, updatable = false)
    private UserEntity user;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "conversation_id", nullable = false, updatable = false)
    private ConversationEntity conversation;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "assistant_message_id", nullable = false, updatable = false)
    private MessageEntity assistantMessage;

    @Column(name = "object_key", nullable = false, unique = true, length = 512)
    private String objectKey;

    @Column(name = "image_model", nullable = false, length = 80)
    private String imageModel;

    @Column(nullable = false, length = 512)
    private String prompt;

    @Column(name = "content_type", nullable = false, length = 100)
    private String contentType;

    @Column(name = "size_bytes", nullable = false)
    private long size;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    protected GeneratedImageEntity() {
    }

    public GeneratedImageEntity(
            UUID id,
            UserEntity user,
            ConversationEntity conversation,
            MessageEntity assistantMessage,
            String objectKey,
            String imageModel,
            String prompt,
            String contentType,
            long size,
            Instant createdAt
    ) {
        this.id = Objects.requireNonNull(id);
        this.user = Objects.requireNonNull(user);
        this.conversation = Objects.requireNonNull(conversation);
        this.assistantMessage = Objects.requireNonNull(assistantMessage);
        this.objectKey = Objects.requireNonNull(objectKey);
        this.imageModel = Objects.requireNonNull(imageModel);
        this.prompt = Objects.requireNonNull(prompt);
        this.contentType = Objects.requireNonNull(contentType);
        this.size = size;
        this.createdAt = Objects.requireNonNull(createdAt);
    }

    public UUID getId() { return id; }
    public UserEntity getUser() { return user; }
    public ConversationEntity getConversation() { return conversation; }
    public MessageEntity getAssistantMessage() { return assistantMessage; }
    public String getObjectKey() { return objectKey; }
    public String getImageModel() { return imageModel; }
    public String getPrompt() { return prompt; }
    public String getContentType() { return contentType; }
    public long getSize() { return size; }
    public Instant getCreatedAt() { return createdAt; }
}
