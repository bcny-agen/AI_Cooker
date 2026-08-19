package com.aicooker.backend.repository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

import com.aicooker.backend.entity.UserMemoryEntity;
import org.springframework.data.jpa.repository.JpaRepository;

public interface UserMemoryRepository
        extends JpaRepository<UserMemoryEntity, UUID> {

    List<UserMemoryEntity> findByUser_IdAndActiveTrue(UUID userId);

    Optional<UserMemoryEntity> findByIdAndUser_IdAndActiveTrue(
            UUID id,
            UUID userId
    );

    Optional<UserMemoryEntity> findByUser_IdAndMemoryKey(
            UUID userId,
            String memoryKey
    );
}
