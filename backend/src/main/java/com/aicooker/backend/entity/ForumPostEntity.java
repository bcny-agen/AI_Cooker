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
@Table(name = "forum_posts")
public class ForumPostEntity {

    @Id
    @JdbcTypeCode(SqlTypes.CHAR)
    @Column(nullable = false, updatable = false, length = 36)
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "author_id", nullable = false, updatable = false)
    private UserEntity author;

    @Column(nullable = false, length = 160)
    private String title;

    @Column(nullable = false, columnDefinition = "LONGTEXT")
    private String content;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "image_id")
    private UploadedImageEntity image;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "generated_image_id")
    private GeneratedImageEntity generatedImage;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "source_conversation_id", updatable = false)
    private ConversationEntity sourceConversation;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    protected ForumPostEntity() {
    }

    public ForumPostEntity(
            UUID id,
            UserEntity author,
            String title,
            String content,
            UploadedImageEntity image,
            ConversationEntity sourceConversation,
            Instant createdAt,
            Instant updatedAt
    ) {
        this(
                id,
                author,
                title,
                content,
                image,
                null,
                sourceConversation,
                createdAt,
                updatedAt
        );
    }

    public ForumPostEntity(
            UUID id,
            UserEntity author,
            String title,
            String content,
            UploadedImageEntity image,
            GeneratedImageEntity generatedImage,
            ConversationEntity sourceConversation,
            Instant createdAt,
            Instant updatedAt
    ) {
        this.id = Objects.requireNonNull(id);
        this.author = Objects.requireNonNull(author);
        this.title = Objects.requireNonNull(title);
        this.content = Objects.requireNonNull(content);
        this.image = image;
        this.generatedImage = generatedImage;
        if (image != null && generatedImage != null) {
            throw new IllegalArgumentException(
                    "A forum post can reference only one image source."
            );
        }
        this.sourceConversation = sourceConversation;
        this.createdAt = Objects.requireNonNull(createdAt);
        this.updatedAt = Objects.requireNonNull(updatedAt);
    }

    public void update(
            String title,
            String content,
            UploadedImageEntity image,
            Instant updatedAt
    ) {
        update(title, content, image, null, updatedAt);
    }

    public void update(
            String title,
            String content,
            UploadedImageEntity image,
            GeneratedImageEntity generatedImage,
            Instant updatedAt
    ) {
        this.title = Objects.requireNonNull(title);
        this.content = Objects.requireNonNull(content);
        this.image = image;
        this.generatedImage = generatedImage;
        if (image != null && generatedImage != null) {
            throw new IllegalArgumentException(
                    "A forum post can reference only one image source."
            );
        }
        this.updatedAt = Objects.requireNonNull(updatedAt);
    }

    public UUID getId() {
        return id;
    }

    public UserEntity getAuthor() {
        return author;
    }

    public String getTitle() {
        return title;
    }

    public String getContent() {
        return content;
    }

    public UploadedImageEntity getImage() {
        return image;
    }

    public GeneratedImageEntity getGeneratedImage() {
        return generatedImage;
    }

    public ConversationEntity getSourceConversation() {
        return sourceConversation;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }
}
