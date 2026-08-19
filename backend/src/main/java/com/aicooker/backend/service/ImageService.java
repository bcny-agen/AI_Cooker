package com.aicooker.backend.service;

import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.time.Clock;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;

import com.aicooker.backend.config.OssProperties;
import com.aicooker.backend.dto.ImageResponse;
import com.aicooker.backend.entity.UploadedImageEntity;
import com.aicooker.backend.entity.UserEntity;
import com.aicooker.backend.exception.ImageNotFoundException;
import com.aicooker.backend.exception.ImageStorageException;
import com.aicooker.backend.exception.ImageTooLargeException;
import com.aicooker.backend.exception.InvalidImageException;
import com.aicooker.backend.repository.UploadedImageRepository;
import com.aicooker.backend.repository.UserRepository;
import com.aicooker.backend.storage.ImageObjectStorage;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

@Service
public class ImageService {

    private static final Logger LOGGER = LoggerFactory.getLogger(ImageService.class);
    private static final Map<String, String> EXTENSIONS = Map.of(
            "image/jpeg", "jpg",
            "image/png", "png",
            "image/webp", "webp"
    );

    private final UploadedImageRepository imageRepository;
    private final UserRepository userRepository;
    private final ImageObjectStorage objectStorage;
    private final OssProperties properties;
    private final Clock clock;

    public ImageService(
            UploadedImageRepository imageRepository,
            UserRepository userRepository,
            ImageObjectStorage objectStorage,
            OssProperties properties,
            Clock clock
    ) {
        this.imageRepository = imageRepository;
        this.userRepository = userRepository;
        this.objectStorage = objectStorage;
        this.properties = properties;
        this.clock = clock;
    }

    public ImageResponse upload(UUID userId, MultipartFile file) {
        ValidatedImage image = validate(file);
        UserEntity owner = userRepository.findById(userId)
                .orElseThrow(() -> new AccessDeniedException(
                        "Authenticated user no longer exists."
                ));

        UUID imageId = UUID.randomUUID();
        String objectKey = "users/%s/images/%s.%s".formatted(
                userId,
                UUID.randomUUID(),
                image.extension()
        );
        boolean uploaded = false;

        try (InputStream inputStream = file.getInputStream()) {
            objectStorage.upload(
                    objectKey,
                    inputStream,
                    file.getSize(),
                    image.contentType()
            );
            uploaded = true;
            URI readUrl = objectStorage.createReadUrl(objectKey);
            var entity = new UploadedImageEntity(
                    imageId,
                    owner,
                    objectKey,
                    safeOriginalFilename(file.getOriginalFilename(), image.extension()),
                    image.contentType(),
                    file.getSize(),
                    clock.instant()
            );
            imageRepository.saveAndFlush(entity);
            return toResponse(entity, readUrl);
        } catch (IOException exception) {
            if (uploaded) {
                cleanupOrphan(objectKey);
            }
            throw new ImageStorageException("The uploaded image could not be read.", exception);
        } catch (DataAccessException | ImageStorageException exception) {
            if (uploaded) {
                cleanupOrphan(objectKey);
            }
            throw exception;
        }
    }

    public ResolvedImage resolveForChat(UUID userId, UUID imageId) {
        ImageResponse image = getImage(userId, imageId);
        return new ResolvedImage(image.imageId(), image.url());
    }

    public ImageResponse getImage(UUID userId, UUID imageId) {
        UploadedImageEntity image = imageRepository
                .findByIdAndUser_Id(imageId, userId)
                .orElseThrow(() -> new ImageNotFoundException(imageId));
        if (!objectStorage.exists(image.getObjectKey())) {
            throw new ImageStorageException(
                    "Image metadata exists but the OSS object is missing."
            );
        }
        URI readUrl = objectStorage.createReadUrl(image.getObjectKey());
        return toResponse(image, readUrl);
    }

    private ValidatedImage validate(MultipartFile file) {
        if (file == null || file.isEmpty() || file.getSize() <= 0) {
            throw new InvalidImageException("Image file must not be empty.");
        }
        if (file.getSize() > properties.maxFileSize().toBytes()) {
            throw new ImageTooLargeException();
        }
        String contentType = file.getContentType() == null
                ? ""
                : file.getContentType().trim().toLowerCase(Locale.ROOT);
        String extension = EXTENSIONS.get(contentType);
        if (extension == null) {
            throw new InvalidImageException("Unsupported image content type.");
        }

        try (InputStream inputStream = file.getInputStream()) {
            byte[] header = inputStream.readNBytes(12);
            if (!matchesSignature(contentType, header)) {
                throw new InvalidImageException(
                        "File content does not match its declared image type."
                );
            }
        } catch (IOException exception) {
            throw new InvalidImageException("Image file could not be validated.", exception);
        }
        return new ValidatedImage(contentType, extension);
    }

    private static boolean matchesSignature(String contentType, byte[] header) {
        return switch (contentType) {
            case "image/jpeg" -> header.length >= 3
                    && unsigned(header[0]) == 0xFF
                    && unsigned(header[1]) == 0xD8
                    && unsigned(header[2]) == 0xFF;
            case "image/png" -> header.length >= 8
                    && unsigned(header[0]) == 0x89
                    && header[1] == 0x50
                    && header[2] == 0x4E
                    && header[3] == 0x47
                    && header[4] == 0x0D
                    && header[5] == 0x0A
                    && header[6] == 0x1A
                    && header[7] == 0x0A;
            case "image/webp" -> header.length >= 12
                    && ascii(header, 0, "RIFF")
                    && ascii(header, 8, "WEBP");
            default -> false;
        };
    }

    private static int unsigned(byte value) {
        return Byte.toUnsignedInt(value);
    }

    private static boolean ascii(byte[] source, int offset, String expected) {
        for (int index = 0; index < expected.length(); index++) {
            if (source[offset + index] != (byte) expected.charAt(index)) {
                return false;
            }
        }
        return true;
    }

    private static String safeOriginalFilename(
            String originalFilename,
            String extension
    ) {
        String candidate = originalFilename == null
                ? ""
                : originalFilename.replace('\\', '/');
        int lastSlash = candidate.lastIndexOf('/');
        if (lastSlash >= 0) {
            candidate = candidate.substring(lastSlash + 1);
        }
        candidate = candidate.replaceAll("[\\p{Cntrl}]", "_").strip();
        if (candidate.isBlank()) {
            candidate = "image." + extension;
        }
        int codePoints = candidate.codePointCount(0, candidate.length());
        if (codePoints > 255) {
            candidate = candidate.substring(0, candidate.offsetByCodePoints(0, 255));
        }
        return candidate;
    }

    private void cleanupOrphan(String objectKey) {
        try {
            objectStorage.delete(objectKey);
        } catch (ImageStorageException cleanupFailure) {
            LOGGER.error(
                    "Failed to clean up orphaned OSS object with key {}",
                    objectKey,
                    cleanupFailure
            );
        }
    }

    private static ImageResponse toResponse(
            UploadedImageEntity image,
            URI readUrl
    ) {
        return new ImageResponse(
                image.getId(),
                readUrl.toString(),
                image.getOriginalFilename(),
                image.getContentType(),
                image.getSize()
        );
    }

    private record ValidatedImage(String contentType, String extension) {
    }

    public record ResolvedImage(UUID imageId, String url) {
    }
}
