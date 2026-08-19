package com.aicooker.backend.service;

import java.net.URI;
import java.util.UUID;

import com.aicooker.backend.dto.ImageResponse;
import com.aicooker.backend.entity.UploadedImageEntity;
import com.aicooker.backend.entity.GeneratedImageEntity;
import com.aicooker.backend.exception.ForumPostImageNotFoundException;
import com.aicooker.backend.exception.ImageStorageException;
import com.aicooker.backend.repository.ForumPostRepository;
import com.aicooker.backend.exception.ForumPostNotFoundException;
import com.aicooker.backend.storage.ImageObjectStorage;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ForumImageService {

    private final ForumPostRepository postRepository;
    private final ImageObjectStorage objectStorage;

    public ForumImageService(
            ForumPostRepository postRepository,
            ImageObjectStorage objectStorage
    ) {
        this.postRepository = postRepository;
        this.objectStorage = objectStorage;
    }

    @Transactional(readOnly = true)
    public ImageResponse createPreview(UUID postId) {
        var post = postRepository.findById(postId)
                .orElseThrow(() -> new ForumPostNotFoundException(postId));
        UploadedImageEntity image = post.getImage();
        GeneratedImageEntity generatedImage = post.getGeneratedImage();
        if (image == null && generatedImage == null) {
            throw new ForumPostImageNotFoundException(postId);
        }
        String objectKey = image != null
                ? image.getObjectKey() : generatedImage.getObjectKey();
        if (!objectStorage.exists(objectKey)) {
            throw new ImageStorageException(
                    "Forum image metadata exists but the OSS object is missing."
            );
        }
        URI readUrl = objectStorage.createReadUrl(objectKey);
        return new ImageResponse(
                image != null ? image.getId() : generatedImage.getId(),
                readUrl.toString(),
                image != null
                        ? image.getOriginalFilename()
                        : generatedFilename(generatedImage.getContentType()),
                image != null
                        ? image.getContentType() : generatedImage.getContentType(),
                image != null ? image.getSize() : generatedImage.getSize()
        );
    }

    private static String generatedFilename(String contentType) {
        String extension = switch (contentType) {
            case "image/jpeg" -> "jpg";
            case "image/webp" -> "webp";
            default -> "png";
        };
        return "ai-generated-dish." + extension;
    }
}
