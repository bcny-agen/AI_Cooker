package com.aicooker.backend.repository;

import java.util.UUID;
import java.util.List;

import com.aicooker.backend.entity.MessageEntity;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.EntityGraph;

public interface MessageRepository extends JpaRepository<MessageEntity, Long> {

    long countByConversation_Id(UUID conversationId);

    Page<MessageEntity> findByConversation_Id(
            UUID conversationId,
            Pageable pageable
    );

    @EntityGraph(attributePaths = {"image", "image.user"})
    List<MessageEntity> findByConversation_IdOrderByCreatedAtAscIdAsc(
            UUID conversationId
    );

    List<MessageEntity> findByConversation_IdAndIdLessThanOrderByCreatedAtAscIdAsc(
            UUID conversationId,
            Long beforeMessageId
    );

    List<MessageEntity> findTop8ByConversation_IdOrderByCreatedAtDescIdDesc(
            UUID conversationId
    );
}
