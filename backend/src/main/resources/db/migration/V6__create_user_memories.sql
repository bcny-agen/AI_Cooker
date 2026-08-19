CREATE TABLE user_memories (
    id CHAR(36) NOT NULL,
    user_id CHAR(36) NOT NULL,
    memory_type VARCHAR(40) NOT NULL,
    memory_key VARCHAR(80) NOT NULL,
    memory_value VARCHAR(255) NOT NULL,
    confidence DECIMAL(5, 4) NOT NULL,
    source_conversation_id CHAR(36) NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT fk_user_memories_user
        FOREIGN KEY (user_id) REFERENCES users (id),
    CONSTRAINT fk_user_memories_source_conversation
        FOREIGN KEY (source_conversation_id) REFERENCES conversations (id)
        ON DELETE SET NULL,
    CONSTRAINT uk_user_memories_user_key UNIQUE (user_id, memory_key),
    INDEX idx_user_memories_active (user_id, active, memory_type, updated_at DESC),
    INDEX idx_user_memories_source (source_conversation_id)
);
