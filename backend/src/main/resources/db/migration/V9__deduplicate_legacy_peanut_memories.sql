UPDATE user_memories
SET active = FALSE,
    updated_at = CURRENT_TIMESTAMP(6)
WHERE id IN (
    SELECT duplicate_id
    FROM (
        SELECT legacy.id AS duplicate_id
        FROM user_memories AS legacy
        INNER JOIN user_memories AS canonical
            ON canonical.user_id = legacy.user_id
            AND canonical.memory_key = 'peanut'
            AND canonical.id <> legacy.id
        WHERE legacy.memory_key IN (
            'peanuts',
            'peanut allergy',
            '花生',
            '花生过敏'
        )
          AND legacy.active = TRUE
    ) AS duplicate_memories
);
