package com.aicooker.backend.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.net.URI;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Optional;
import java.util.UUID;

import com.aicooker.backend.config.OssProperties;
import com.aicooker.backend.entity.UploadedImageEntity;
import com.aicooker.backend.entity.UserEntity;
import com.aicooker.backend.exception.ImageNotFoundException;
import com.aicooker.backend.exception.ImageStorageException;
import com.aicooker.backend.exception.ImageTooLargeException;
import com.aicooker.backend.exception.InvalidImageException;
import com.aicooker.backend.repository.UploadedImageRepository;
import com.aicooker.backend.repository.UserRepository;
import com.aicooker.backend.storage.ImageObjectStorage;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.util.unit.DataSize;
import org.springframework.web.multipart.MultipartFile;

@ExtendWith(MockitoExtension.class)
class ImageServiceTest {

    private static final UUID USER_ID =
            UUID.fromString("0f0c2f0d-a51b-44f6-915b-ed9d3f583804");
    private static final Instant NOW = Instant.parse("2026-08-07T12:00:00Z");
    private static final byte[] JPEG_BYTES = {
            (byte) 0xFF, (byte) 0xD8, (byte) 0xFF, 0x01, 0x02, 0x03
    };

    @Mock
    private UploadedImageRepository imageRepository;

    @Mock
    private UserRepository userRepository;

    @Mock
    private ImageObjectStorage objectStorage;

    private ImageService imageService;
    private UserEntity user;

    @BeforeEach
    void setUp() {
        var properties = new OssProperties(
                URI.create("https://oss-cn-hangzhou.aliyuncs.com"),
                "cn-hangzhou",
                "test-bucket",
                "test-key-id",
                "test-key-secret",
                Duration.ofMinutes(15),
                DataSize.ofMegabytes(10)
        );
        imageService = new ImageService(
                imageRepository,
                userRepository,
                objectStorage,
                properties,
                Clock.fixed(NOW, ZoneOffset.UTC)
        );
        user = new UserEntity(USER_ID, "alice", "hash", NOW, NOW);
    }

    @Test
    void uploadsValidImageWithGeneratedKeyAndPersistsMetadata() {
        var file = new MockMultipartFile(
                "file",
                "../unsafe/ingredients.jpg",
                "image/jpeg",
                JPEG_BYTES
        );
        when(userRepository.findById(USER_ID)).thenReturn(Optional.of(user));
        when(objectStorage.createReadUrl(anyString())).thenReturn(
                URI.create("https://signed.example/image?signature=secret")
        );
        when(imageRepository.saveAndFlush(any(UploadedImageEntity.class)))
                .thenAnswer(invocation -> invocation.getArgument(0));

        var response = imageService.upload(USER_ID, file);

        var keyCaptor = ArgumentCaptor.forClass(String.class);
        verify(objectStorage).upload(
                keyCaptor.capture(),
                any(),
                org.mockito.ArgumentMatchers.eq((long) JPEG_BYTES.length),
                org.mockito.ArgumentMatchers.eq("image/jpeg")
        );
        assertThat(keyCaptor.getValue()).matches(
                "users/" + USER_ID
                        + "/images/[0-9a-f-]{36}\\.jpg"
        );
        var entityCaptor = ArgumentCaptor.forClass(UploadedImageEntity.class);
        verify(imageRepository).saveAndFlush(entityCaptor.capture());
        assertThat(entityCaptor.getValue().getObjectKey())
                .isEqualTo(keyCaptor.getValue());
        assertThat(entityCaptor.getValue().getUser().getId()).isEqualTo(USER_ID);
        assertThat(response.originalFilename()).isEqualTo("ingredients.jpg");
        assertThat(response.contentType()).isEqualTo("image/jpeg");
        assertThat(response.size()).isEqualTo(JPEG_BYTES.length);
    }

    @Test
    void rejectsUnsupportedContentTypeBeforeCallingOss() {
        var file = new MockMultipartFile(
                "file",
                "ingredients.txt",
                "text/plain",
                JPEG_BYTES
        );

        assertThatThrownBy(() -> imageService.upload(USER_ID, file))
                .isInstanceOf(InvalidImageException.class);
        verify(objectStorage, never()).upload(anyString(), any(), anyLong(), anyString());
    }

    @Test
    void rejectsOversizedImageBeforeCallingOss() {
        MultipartFile file = org.mockito.Mockito.mock(MultipartFile.class);
        when(file.isEmpty()).thenReturn(false);
        when(file.getSize()).thenReturn(DataSize.ofMegabytes(10).toBytes() + 1);

        assertThatThrownBy(() -> imageService.upload(USER_ID, file))
                .isInstanceOf(ImageTooLargeException.class);
        verify(objectStorage, never()).upload(anyString(), any(), anyLong(), anyString());
    }

    @Test
    void propagatesOssUploadFailureWithoutSavingMetadata() {
        var file = jpegFile();
        when(userRepository.findById(USER_ID)).thenReturn(Optional.of(user));
        org.mockito.Mockito.doThrow(new ImageStorageException("OSS unavailable"))
                .when(objectStorage)
                .upload(anyString(), any(), anyLong(), anyString());

        assertThatThrownBy(() -> imageService.upload(USER_ID, file))
                .isInstanceOf(ImageStorageException.class);
        verify(imageRepository, never()).saveAndFlush(any());
    }

    @Test
    void removesUploadedObjectWhenMetadataPersistenceFails() {
        var file = jpegFile();
        when(userRepository.findById(USER_ID)).thenReturn(Optional.of(user));
        when(objectStorage.createReadUrl(anyString())).thenReturn(
                URI.create("https://signed.example/image")
        );
        when(imageRepository.saveAndFlush(any())).thenThrow(
                new DataIntegrityViolationException("database unavailable")
        );

        assertThatThrownBy(() -> imageService.upload(USER_ID, file))
                .isInstanceOf(DataIntegrityViolationException.class);
        var keyCaptor = ArgumentCaptor.forClass(String.class);
        verify(objectStorage).delete(keyCaptor.capture());
        assertThat(keyCaptor.getValue()).startsWith("users/" + USER_ID + "/images/");
    }

    @Test
    void resolvesOwnedImageToFreshSignedUrl() {
        UUID imageId = UUID.randomUUID();
        var image = storedImage(imageId);
        when(imageRepository.findByIdAndUser_Id(imageId, USER_ID))
                .thenReturn(Optional.of(image));
        when(objectStorage.exists(image.getObjectKey())).thenReturn(true);
        when(objectStorage.createReadUrl(image.getObjectKey())).thenReturn(
                URI.create("https://signed.example/fresh-url")
        );

        var resolved = imageService.resolveForChat(USER_ID, imageId);

        assertThat(resolved.imageId()).isEqualTo(imageId);
        assertThat(resolved.url()).isEqualTo("https://signed.example/fresh-url");
    }

    @Test
    void hidesImagesOwnedByAnotherUser() {
        UUID imageId = UUID.randomUUID();
        when(imageRepository.findByIdAndUser_Id(imageId, USER_ID))
                .thenReturn(Optional.empty());

        assertThatThrownBy(() -> imageService.resolveForChat(USER_ID, imageId))
                .isInstanceOf(ImageNotFoundException.class);
        verify(objectStorage, never()).createReadUrl(anyString());
    }

    @Test
    void reportsMissingOssObjectForExistingMetadata() {
        UUID imageId = UUID.randomUUID();
        var image = storedImage(imageId);
        when(imageRepository.findByIdAndUser_Id(imageId, USER_ID))
                .thenReturn(Optional.of(image));
        when(objectStorage.exists(image.getObjectKey())).thenReturn(false);

        assertThatThrownBy(() -> imageService.resolveForChat(USER_ID, imageId))
                .isInstanceOf(ImageStorageException.class);
        verify(objectStorage, never()).createReadUrl(anyString());
    }

    private static MockMultipartFile jpegFile() {
        return new MockMultipartFile(
                "file",
                "ingredients.jpg",
                "image/jpeg",
                JPEG_BYTES
        );
    }

    private UploadedImageEntity storedImage(UUID imageId) {
        return new UploadedImageEntity(
                imageId,
                user,
                "users/%s/images/%s.jpg".formatted(USER_ID, imageId),
                "ingredients.jpg",
                "image/jpeg",
                JPEG_BYTES.length,
                NOW
        );
    }
}
