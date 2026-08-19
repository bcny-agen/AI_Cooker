package com.aicooker.backend.repository;

import java.util.Optional;
import java.util.UUID;

import com.aicooker.backend.entity.ForumPostEntity;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ForumPostRepository extends JpaRepository<ForumPostEntity, UUID> {

    @Override
    @EntityGraph(attributePaths = {"author", "image"})
    Page<ForumPostEntity> findAll(Pageable pageable);

    @EntityGraph(attributePaths = {"author", "image"})
    Page<ForumPostEntity> findByAuthor_Id(UUID authorId, Pageable pageable);

    @Override
    @EntityGraph(attributePaths = {"author", "image"})
    Optional<ForumPostEntity> findById(UUID id);

    @EntityGraph(attributePaths = {"author", "image"})
    Optional<ForumPostEntity> findByIdAndAuthor_Id(UUID id, UUID authorId);

    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query(
            value = """
                    UPDATE forum_posts
                    SET source_conversation_id = NULL
                    WHERE source_conversation_id = :conversationId
                    """,
            nativeQuery = true
    )
    int clearSourceConversation(
            @Param("conversationId") String conversationId
    );
}
