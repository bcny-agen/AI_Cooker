package com.aicooker.backend.entity;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

@Entity
@Table(name = "user_memories")
public class UserMemoryEntity {

    @Id
    @JdbcTypeCode(SqlTypes.CHAR)
    @Column(nullable = false, updatable = false, length = 36)
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false, updatable = false)
    private UserEntity user;

    @Enumerated(EnumType.STRING)
    @Column(name = "memory_type", nullable = false, length = 40)
    private MemoryType memoryType;

    @Column(name = "memory_key", nullable = false, length = 80)
    private String memoryKey;

    @Column(name = "memory_value", nullable = false, length = 255)
    private String memoryValue;

    @Column(nullable = false, precision = 5, scale = 4)
    private BigDecimal confidence;

    @JdbcTypeCode(SqlTypes.CHAR)
    @Column(name = "source_conversation_id", length = 36)
    private UUID sourceConversationId;

    @Column(nullable = false)
    private boolean active;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    protected UserMemoryEntity() {
    }

    public UserMemoryEntity(
            UUID id,
            UserEntity user,
            MemoryType memoryType,
            String memoryKey,
            String memoryValue,
            BigDecimal confidence,
            UUID sourceConversationId,
            Instant createdAt
    ) {
        this.id = Objects.requireNonNull(id);
        this.user = Objects.requireNonNull(user);
        this.memoryType = Objects.requireNonNull(memoryType);
        this.memoryKey = Objects.requireNonNull(memoryKey);
        this.memoryValue = Objects.requireNonNull(memoryValue);
        this.confidence = Objects.requireNonNull(confidence);
        this.sourceConversationId = sourceConversationId;
        this.active = true;
        this.createdAt = Objects.requireNonNull(createdAt);
        this.updatedAt = createdAt;
    }

    public void reinforceOrReplace(
            MemoryType memoryType,
            String memoryValue,
            BigDecimal confidence,
            UUID sourceConversationId,
            Instant updatedAt
    ) {
        this.memoryType = Objects.requireNonNull(memoryType);
        this.memoryValue = Objects.requireNonNull(memoryValue);
        this.confidence = Objects.requireNonNull(confidence);
        this.sourceConversationId = sourceConversationId;
        this.active = true;
        this.updatedAt = Objects.requireNonNull(updatedAt);
    }

    public void deactivate(Instant updatedAt) {
        this.active = false;
        this.updatedAt = Objects.requireNonNull(updatedAt);
    }

    public void correct(
            MemoryType memoryType,
            String memoryKey,
            String memoryValue,
            Instant updatedAt
    ) {
        this.memoryType = Objects.requireNonNull(memoryType);
        this.memoryKey = Objects.requireNonNull(memoryKey);
        this.memoryValue = Objects.requireNonNull(memoryValue);
        this.confidence = BigDecimal.ONE.setScale(4);
        this.active = true;
        this.updatedAt = Objects.requireNonNull(updatedAt);
    }

    public UUID getId() {
        return id;
    }

    public UserEntity getUser() {
        return user;
    }

    public MemoryType getMemoryType() {
        return memoryType;
    }

    public String getMemoryKey() {
        return memoryKey;
    }

    public String getMemoryValue() {
        return memoryValue;
    }

    public BigDecimal getConfidence() {
        return confidence;
    }

    public UUID getSourceConversationId() {
        return sourceConversationId;
    }

    public boolean isActive() {
        return active;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }
}
