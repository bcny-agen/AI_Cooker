package com.aicooker.backend.service;

import java.time.Clock;
import java.util.UUID;

import com.aicooker.backend.dto.CreateForumPostRequest;
import com.aicooker.backend.dto.ForumAuthorResponse;
import com.aicooker.backend.dto.ForumPostResponse;
import com.aicooker.backend.dto.PageResponse;
import com.aicooker.backend.dto.UpdateForumPostRequest;
import com.aicooker.backend.entity.ForumPostEntity;
import com.aicooker.backend.entity.ForumImageType;
import com.aicooker.backend.entity.GeneratedImageEntity;
import com.aicooker.backend.entity.UploadedImageEntity;
import com.aicooker.backend.exception.ForumPostNotFoundException;
import com.aicooker.backend.exception.ConversationNotFoundException;
import com.aicooker.backend.repository.ConversationRepository;
import com.aicooker.backend.exception.ImageNotFoundException;
import com.aicooker.backend.exception.GeneratedImageNotFoundException;
import com.aicooker.backend.repository.ForumPostRepository;
import com.aicooker.backend.repository.GeneratedImageRepository;
import com.aicooker.backend.repository.UploadedImageRepository;
import com.aicooker.backend.repository.UserRepository;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ForumPostService {

    private static final Sort FEED_ORDER = Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.desc("id")
    );

    private final ForumPostRepository postRepository;
    private final UserRepository userRepository;
    private final UploadedImageRepository imageRepository;
    private final GeneratedImageRepository generatedImageRepository;
    private final ConversationRepository conversationRepository;
    private final Clock clock;

    public ForumPostService(
            ForumPostRepository postRepository,
            UserRepository userRepository,
            UploadedImageRepository imageRepository,
            GeneratedImageRepository generatedImageRepository,
            ConversationRepository conversationRepository,
            Clock clock
    ) {
        this.postRepository = postRepository;
        this.userRepository = userRepository;
        this.imageRepository = imageRepository;
        this.generatedImageRepository = generatedImageRepository;
        this.conversationRepository = conversationRepository;
        this.clock = clock;
    }

    @Transactional
    public ForumPostResponse create(UUID userId, CreateForumPostRequest request) {
        var author = userRepository.findById(userId)
                .orElseThrow(() -> new AccessDeniedException(
                        "Authenticated user no longer exists."
                ));
        SelectedImage image = resolveOwnedImage(
                userId,
                request.imageId(),
                request.imageType()
        );
        var sourceConversation = request.sourceConversationId() == null
                ? null
                : conversationRepository.findByIdAndUser_Id(
                        request.sourceConversationId(),
                        userId
                ).orElseThrow(() -> new ConversationNotFoundException(
                        request.sourceConversationId()
                ));
        var now = clock.instant();
        var post = new ForumPostEntity(
                UUID.randomUUID(),
                author,
                normalizeTitle(request.title()),
                normalizeContent(request.content()),
                image.uploaded(),
                image.generated(),
                sourceConversation,
                now,
                now
        );
        return toResponse(postRepository.save(post), userId);
    }

    @Transactional(readOnly = true)
    public PageResponse<ForumPostResponse> list(UUID userId, int page, int size) {
        return PageResponse.from(postRepository
                .findAll(PageRequest.of(page, size, FEED_ORDER))
                .map(post -> toResponse(post, userId)));
    }

    @Transactional(readOnly = true)
    public PageResponse<ForumPostResponse> listMine(
            UUID userId,
            int page,
            int size
    ) {
        return PageResponse.from(postRepository
                .findByAuthor_Id(userId, PageRequest.of(page, size, FEED_ORDER))
                .map(post -> toResponse(post, userId)));
    }

    @Transactional(readOnly = true)
    public ForumPostResponse get(UUID userId, UUID postId) {
        ForumPostEntity post = postRepository.findById(postId)
                .orElseThrow(() -> new ForumPostNotFoundException(postId));
        return toResponse(post, userId);
    }

    @Transactional
    public ForumPostResponse update(
            UUID userId,
            UUID postId,
            UpdateForumPostRequest request
    ) {
        ForumPostEntity post = postRepository
                .findByIdAndAuthor_Id(postId, userId)
                .orElseThrow(() -> new ForumPostNotFoundException(postId));
        SelectedImage image = resolveOwnedImage(
                userId,
                request.imageId(),
                request.imageType()
        );
        post.update(
                normalizeTitle(request.title()),
                normalizeContent(request.content()),
                image.uploaded(),
                image.generated(),
                clock.instant()
        );
        return toResponse(post, userId);
    }

    @Transactional
    public void delete(UUID userId, UUID postId) {
        ForumPostEntity post = postRepository
                .findByIdAndAuthor_Id(postId, userId)
                .orElseThrow(() -> new ForumPostNotFoundException(postId));
        postRepository.delete(post);
    }

    private SelectedImage resolveOwnedImage(
            UUID userId,
            UUID imageId,
            ForumImageType imageType
    ) {
        if (imageId == null) {
            return new SelectedImage(null, null);
        }
        if (imageType == null) {
            throw new ImageNotFoundException(imageId);
        }
        return switch (imageType) {
            case USER_UPLOAD -> new SelectedImage(
                    imageRepository.findByIdAndUser_Id(imageId, userId)
                            .orElseThrow(() -> new ImageNotFoundException(imageId)),
                    null
            );
            case AI_GENERATED -> new SelectedImage(
                    null,
                    resolveOwnedGeneratedImage(userId, imageId)
            );
        };
    }

    private GeneratedImageEntity resolveOwnedGeneratedImage(
            UUID userId,
            UUID imageId
    ) {
        return generatedImageRepository.findByIdAndUser_Id(imageId, userId)
                .filter(image -> image.getConversation().getUser().getId()
                        .equals(userId))
                .filter(image -> image.getAssistantMessage().getConversation()
                        .getId().equals(image.getConversation().getId()))
                .filter(image -> image.getAssistantMessage().getRole()
                        == com.aicooker.backend.entity.MessageRole.ASSISTANT)
                .orElseThrow(() -> new GeneratedImageNotFoundException(imageId));
    }

    private static ForumPostResponse toResponse(
            ForumPostEntity post,
            UUID viewerId
    ) {
        return new ForumPostResponse(
                post.getId(),
                post.getTitle(),
                post.getContent(),
                new ForumAuthorResponse(
                        post.getAuthor().getId(),
                        post.getAuthor().getUsername()
                ),
                post.getImage() != null
                        ? post.getImage().getId()
                        : post.getGeneratedImage() == null
                                ? null : post.getGeneratedImage().getId(),
                post.getImage() != null
                        ? ForumImageType.USER_UPLOAD
                        : post.getGeneratedImage() == null
                                ? null : ForumImageType.AI_GENERATED,
                post.getCreatedAt(),
                post.getUpdatedAt(),
                post.getAuthor().getId().equals(viewerId)
        );
    }

    private static String normalizeTitle(String title) {
        return title.strip();
    }

    private static String normalizeContent(String content) {
        return content.strip();
    }

    private record SelectedImage(
            UploadedImageEntity uploaded,
            GeneratedImageEntity generated
    ) {
    }
}
