package com.aicooker.backend.repository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

import com.aicooker.backend.entity.GeneratedImageEntity;
import org.springframework.data.jpa.repository.JpaRepository;

public interface GeneratedImageRepository
        extends JpaRepository<GeneratedImageEntity, UUID> {

    Optional<GeneratedImageEntity> findByIdAndUser_Id(UUID id, UUID userId);

    Optional<GeneratedImageEntity>
    findFirstByConversation_IdAndUser_IdOrderByCreatedAtDescIdDesc(
            UUID conversationId,
            UUID userId
    );

    List<GeneratedImageEntity>
    findByAssistantMessage_IdInOrderByCreatedAtAscIdAsc(List<Long> messageIds);
}
