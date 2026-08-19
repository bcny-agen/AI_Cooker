package com.aicooker.backend.repository;

import java.util.Optional;
import java.util.UUID;

import com.aicooker.backend.entity.UploadedImageEntity;
import org.springframework.data.jpa.repository.JpaRepository;

public interface UploadedImageRepository
        extends JpaRepository<UploadedImageEntity, UUID> {

    Optional<UploadedImageEntity> findByIdAndUser_Id(
            UUID id,
            UUID userId
    );
}
