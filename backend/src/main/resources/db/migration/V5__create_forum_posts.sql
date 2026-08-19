CREATE TABLE forum_posts (
    id CHAR(36) NOT NULL,
    author_id CHAR(36) NOT NULL,
    title VARCHAR(160) NOT NULL,
    content LONGTEXT NOT NULL,
    image_id CHAR(36) NULL,
    source_conversation_id CHAR(36) NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT fk_forum_posts_author
        FOREIGN KEY (author_id) REFERENCES users (id),
    CONSTRAINT fk_forum_posts_image
        FOREIGN KEY (image_id) REFERENCES uploaded_images (id),
    CONSTRAINT fk_forum_posts_source_conversation
        FOREIGN KEY (source_conversation_id) REFERENCES conversations (id),
    INDEX idx_forum_posts_feed (created_at DESC, id DESC),
    INDEX idx_forum_posts_author_feed (author_id, created_at DESC, id DESC),
    INDEX idx_forum_posts_image (image_id),
    INDEX idx_forum_posts_source_conversation (source_conversation_id)
);
