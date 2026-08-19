package com.aicooker.backend.repository;

import java.util.Optional;
import java.util.UUID;

import com.aicooker.backend.entity.ConversationEntity;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ConversationRepository
        extends JpaRepository<ConversationEntity, UUID> {

    Page<ConversationEntity> findByUser_Id(UUID userId, Pageable pageable);

    Optional<ConversationEntity> findByIdAndUser_Id(UUID id, UUID userId);
}
