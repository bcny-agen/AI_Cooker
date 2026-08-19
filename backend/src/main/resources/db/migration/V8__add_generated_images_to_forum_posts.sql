ALTER TABLE forum_posts
    ADD COLUMN generated_image_id CHAR(36) NULL;

ALTER TABLE forum_posts
    ADD CONSTRAINT fk_forum_posts_generated_image
        FOREIGN KEY (generated_image_id) REFERENCES generated_images (id)
        ON DELETE SET NULL;

CREATE INDEX idx_forum_posts_generated_image
    ON forum_posts (generated_image_id);
