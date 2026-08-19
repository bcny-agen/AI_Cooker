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
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import com.aicooker.backend.client.AiCookerClient;
import com.aicooker.backend.entity.ConversationEntity;
import com.aicooker.backend.entity.GeneratedImageEntity;
import com.aicooker.backend.entity.MessageEntity;
import com.aicooker.backend.entity.MessageRole;
import com.aicooker.backend.entity.ModelId;
import com.aicooker.backend.entity.UserEntity;
import com.aicooker.backend.exception.GeneratedImageNotFoundException;
import com.aicooker.backend.exception.ImageStorageException;
import com.aicooker.backend.repository.ConversationRepository;
import com.aicooker.backend.repository.GeneratedImageRepository;
import com.aicooker.backend.repository.MessageRepository;
import com.aicooker.backend.repository.UserRepository;
import com.aicooker.backend.storage.ImageObjectStorage;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.dao.DataIntegrityViolationException;

@ExtendWith(MockitoExtension.class)
class GeneratedImageServiceTest {

    private static final UUID USER_ID = UUID.fromString(
            "0f0c2f0d-a51b-44f6-915b-ed9d3f583804"
    );
    private static final UUID CONVERSATION_ID = UUID.fromString(
            "9b677223-0733-4d89-b13a-33f2a08ea610"
    );
    private static final UUID GENERATION_ID = UUID.fromString(
            "26806f88-d8fe-4de2-972a-c4482458f134"
    );
    private static final Instant NOW = Instant.parse("2026-08-09T12:00:00Z");
    private static final byte[] PNG = {
            (byte) 0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x01
    };

    @Mock private AiCookerClient aiCookerClient;
    @Mock private ImageObjectStorage objectStorage;
    @Mock private GeneratedImageRepository generatedImageRepository;
    @Mock private UserRepository userRepository;
    @Mock private ConversationRepository conversationRepository;
    @Mock private MessageRepository messageRepository;

    private GeneratedImageService service;
    private UserEntity user;
    private ConversationEntity conversation;
    private MessageEntity assistantMessage;

    @BeforeEach
    void setUp() {
        service = new GeneratedImageService(
                aiCookerClient,
                objectStorage,
                generatedImageRepository,
                userRepository,
                conversationRepository,
                messageRepository,
                Clock.fixed(NOW, ZoneOffset.UTC)
        );
        user = new UserEntity(USER_ID, "alice", "hash", NOW, NOW);
        conversation = new ConversationEntity(
                CONVERSATION_ID,
                user,
                "Dinner",
                ModelId.STEP_FLASH_3_7,
                NOW,
                NOW
        );
        assistantMessage = new MessageEntity(
                conversation,
                MessageRole.ASSISTANT,
                "Here is the image.",
                null,
                NOW
        );
    }

    @Test
    void storesPrivateObjectMetadataAndReturnsSignedPreview() {
        stubOwnedRecords();
        when(aiCookerClient.downloadGeneratedImage(GENERATION_ID))
                .thenReturn(new AiCookerClient.GeneratedImagePayload(
                        PNG, "image/png"
                ));
        when(generatedImageRepository.saveAndFlush(any()))
                .thenAnswer(invocation -> invocation.getArgument(0));
        when(objectStorage.createReadUrl(anyString())).thenReturn(
                URI.create("https://signed.example/generated.png?signature=temporary")
        );

        var response = service.store(
                USER_ID,
                CONVERSATION_ID,
                41L,
                reference()
        );

        var key = ArgumentCaptor.forClass(String.class);
        verify(objectStorage).upload(
                key.capture(), any(), anyLong(),
                org.mockito.ArgumentMatchers.eq("image/png")
        );
        assertThat(key.getValue()).matches(
                "users/" + USER_ID + "/generated/[0-9a-f-]{36}\\.png"
        );
        var metadata = ArgumentCaptor.forClass(GeneratedImageEntity.class);
        verify(generatedImageRepository).saveAndFlush(metadata.capture());
        assertThat(metadata.getValue().getPrompt())
                .isEqualTo("A grounded tomato eggs photo");
        assertThat(metadata.getValue().getImageModel())
                .isEqualTo("step-image-edit-2");
        assertThat(response.url()).startsWith("https://signed.example/");
    }

    @Test
    void anotherUserCannotReadGeneratedImage() {
        UUID imageId = UUID.randomUUID();
        when(generatedImageRepository.findByIdAndUser_Id(imageId, USER_ID))
                .thenReturn(Optional.empty());

        assertThatThrownBy(() -> service.get(USER_ID, imageId))
                .isInstanceOf(GeneratedImageNotFoundException.class);
        verify(objectStorage, never()).createReadUrl(anyString());
    }

    @Test
    void databaseFailureDeletesUploadedOrphan() {
        stubOwnedRecords();
        when(aiCookerClient.downloadGeneratedImage(GENERATION_ID))
                .thenReturn(new AiCookerClient.GeneratedImagePayload(
                        PNG, "image/png"
                ));
        when(generatedImageRepository.saveAndFlush(any())).thenThrow(
                new DataIntegrityViolationException("database unavailable")
        );

        assertThatThrownBy(() -> service.store(
                USER_ID, CONVERSATION_ID, 41L, reference()
        )).isInstanceOf(DataIntegrityViolationException.class);
        verify(objectStorage).delete(anyString());
    }

    @Test
    void historyReloadUsesFreshSignedUrl() {
        MessageEntity message = org.mockito.Mockito.mock(MessageEntity.class);
        when(message.getId()).thenReturn(41L);
        var entity = new GeneratedImageEntity(
                UUID.randomUUID(), user, conversation, message,
                "users/owner/generated/image.png",
                "step-image-edit-2",
                "A food photo",
                "image/png",
                PNG.length,
                NOW
        );
        when(generatedImageRepository
                .findByAssistantMessage_IdInOrderByCreatedAtAscIdAsc(List.of(41L)))
                .thenReturn(List.of(entity));
        when(objectStorage.exists(entity.getObjectKey())).thenReturn(true);
        when(objectStorage.createReadUrl(entity.getObjectKey())).thenReturn(
                URI.create("https://signed.example/fresh")
        );

        var response = service.forMessages(USER_ID, List.of(41L));

        assertThat(response.get(41L)).singleElement().satisfies(image ->
                assertThat(image.url()).isEqualTo("https://signed.example/fresh")
        );
    }

    private void stubOwnedRecords() {
        when(userRepository.findById(USER_ID)).thenReturn(Optional.of(user));
        when(conversationRepository.findByIdAndUser_Id(
                CONVERSATION_ID, USER_ID
        )).thenReturn(Optional.of(conversation));
        when(messageRepository.findById(41L))
                .thenReturn(Optional.of(assistantMessage));
    }

    private static AiCookerClient.GeneratedImageReference reference() {
        return new AiCookerClient.GeneratedImageReference(
                GENERATION_ID,
                "step-image-edit-2",
                "A grounded tomato eggs photo"
        );
    }
}
