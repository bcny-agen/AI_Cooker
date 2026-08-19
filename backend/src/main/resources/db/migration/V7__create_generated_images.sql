CREATE TABLE generated_images (
    id CHAR(36) NOT NULL,
    user_id CHAR(36) NOT NULL,
    conversation_id CHAR(36) NOT NULL,
    assistant_message_id BIGINT NOT NULL,
    object_key VARCHAR(512) NOT NULL,
    image_model VARCHAR(80) NOT NULL,
    prompt VARCHAR(512) NOT NULL,
    content_type VARCHAR(100) NOT NULL,
    size_bytes BIGINT NOT NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uk_generated_images_object_key UNIQUE (object_key),
    CONSTRAINT fk_generated_images_user
        FOREIGN KEY (user_id) REFERENCES users (id),
    CONSTRAINT fk_generated_images_conversation
        FOREIGN KEY (conversation_id) REFERENCES conversations (id),
    CONSTRAINT fk_generated_images_assistant_message
        FOREIGN KEY (assistant_message_id) REFERENCES messages (id)
        ON DELETE CASCADE,
    INDEX idx_generated_images_user_created (user_id, created_at DESC, id),
    INDEX idx_generated_images_conversation (conversation_id, created_at, id),
    INDEX idx_generated_images_message (assistant_message_id, created_at, id)
);
