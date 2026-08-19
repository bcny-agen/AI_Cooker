CREATE TABLE conversations (
    id CHAR(36) NOT NULL,
    title VARCHAR(160) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL,
    updated_at TIMESTAMP(6) NOT NULL,
    CONSTRAINT pk_conversations PRIMARY KEY (id)
);

CREATE INDEX idx_conversations_updated_at
    ON conversations (updated_at, id);

CREATE TABLE messages (
    id BIGINT NOT NULL AUTO_INCREMENT,
    conversation_id CHAR(36) NOT NULL,
    message_role VARCHAR(20) NOT NULL,
    content LONGTEXT NOT NULL,
    image_url VARCHAR(2048) NULL,
    created_at TIMESTAMP(6) NOT NULL,
    CONSTRAINT pk_messages PRIMARY KEY (id),
    CONSTRAINT fk_messages_conversation
        FOREIGN KEY (conversation_id)
        REFERENCES conversations (id)
        ON DELETE CASCADE,
    CONSTRAINT chk_messages_role
        CHECK (message_role IN ('USER', 'ASSISTANT'))
);

CREATE INDEX idx_messages_conversation_order
    ON messages (conversation_id, created_at, id);
