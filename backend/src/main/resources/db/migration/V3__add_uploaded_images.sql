CREATE TABLE uploaded_images (
    id CHAR(36) NOT NULL,
    user_id CHAR(36) NOT NULL,
    object_key VARCHAR(512) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    content_type VARCHAR(100) NOT NULL,
    size_bytes BIGINT NOT NULL,
    created_at TIMESTAMP(6) NOT NULL,
    CONSTRAINT pk_uploaded_images PRIMARY KEY (id),
    CONSTRAINT uk_uploaded_images_object_key UNIQUE (object_key),
    CONSTRAINT fk_uploaded_images_user
        FOREIGN KEY (user_id)
        REFERENCES users (id)
);

CREATE INDEX idx_uploaded_images_user_created
    ON uploaded_images (user_id, created_at, id);

ALTER TABLE messages
    ADD COLUMN image_id CHAR(36) NULL;

ALTER TABLE messages
    ADD CONSTRAINT fk_messages_image
        FOREIGN KEY (image_id)
        REFERENCES uploaded_images (id);

CREATE INDEX idx_messages_image
    ON messages (image_id);

-- The V1 image_url column is intentionally retained so old rows are not lost.
-- New messages use image_id as the durable reference.
