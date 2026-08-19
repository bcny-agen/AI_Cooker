package com.aicooker.backend.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.reset;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.mockito.ArgumentMatchers.eq;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.net.URI;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

import com.aicooker.backend.entity.ForumPostEntity;
import com.aicooker.backend.entity.GeneratedImageEntity;
import com.aicooker.backend.entity.ConversationEntity;
import com.aicooker.backend.entity.MessageEntity;
import com.aicooker.backend.entity.MessageRole;
import com.aicooker.backend.entity.ModelId;
import com.aicooker.backend.entity.UploadedImageEntity;
import com.aicooker.backend.entity.UserEntity;
import com.aicooker.backend.repository.ConversationRepository;
import com.aicooker.backend.repository.ForumPostRepository;
import com.aicooker.backend.repository.GeneratedImageRepository;
import com.aicooker.backend.repository.MessageRepository;
import com.aicooker.backend.repository.UploadedImageRepository;
import com.aicooker.backend.repository.UserRepository;
import com.aicooker.backend.client.AiCookerClient;
import com.aicooker.backend.security.JwtService;
import com.aicooker.backend.storage.ImageObjectStorage;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class ForumIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private ForumPostRepository postRepository;

    @Autowired
    private MessageRepository messageRepository;

    @Autowired
    private ConversationRepository conversationRepository;

    @Autowired
    private UploadedImageRepository imageRepository;

    @Autowired
    private GeneratedImageRepository generatedImageRepository;

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private PasswordEncoder passwordEncoder;

    @Autowired
    private JwtService jwtService;

    @MockitoBean
    private ImageObjectStorage objectStorage;

    @MockitoBean
    private AiCookerClient aiCookerClient;

    @BeforeEach
    void cleanDatabase() {
        postRepository.deleteAllInBatch();
        generatedImageRepository.deleteAllInBatch();
        messageRepository.deleteAllInBatch();
        conversationRepository.deleteAllInBatch();
        imageRepository.deleteAllInBatch();
        userRepository.deleteAllInBatch();
        reset(objectStorage, aiCookerClient);
    }

    @Test
    void createsListsPaginatesAndReturnsPostDetailsAndMine() throws Exception {
        UserEntity alice = createUser("alice");
        UserEntity bob = createUser("bob");
        ForumPostEntity older = postRepository.saveAndFlush(new ForumPostEntity(
                UUID.randomUUID(),
                bob,
                "Older soup",
                "An older community post.",
                null,
                null,
                Instant.parse("2026-08-01T10:00:00Z"),
                Instant.parse("2026-08-01T10:00:00Z")
        ));

        String createdBody = mockMvc.perform(post("/api/forum/posts")
                        .header("Authorization", bearer(alice))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "title": "  Tomato and egg  ",
                                  "content": "  Cooked this tonight.  ",
                                  "imageId": null
                                }
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.title").value("Tomato and egg"))
                .andExpect(jsonPath("$.content").value("Cooked this tonight."))
                .andExpect(jsonPath("$.author.username").value("alice"))
                .andExpect(jsonPath("$.isOwner").value(true))
                .andReturn().getResponse().getContentAsString();
        UUID createdId = UUID.fromString(
                objectMapper.readTree(createdBody).get("id").asText()
        );

        mockMvc.perform(get("/api/forum/posts")
                        .header("Authorization", bearer(bob))
                        .param("page", "0")
                        .param("size", "1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.totalElements").value(2))
                .andExpect(jsonPath("$.totalPages").value(2))
                .andExpect(jsonPath("$.content[0].id")
                        .value(createdId.toString()))
                .andExpect(jsonPath("$.content[0].isOwner").value(false));

        mockMvc.perform(get("/api/forum/posts")
                        .header("Authorization", bearer(bob))
                        .param("page", "1")
                        .param("size", "1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content[0].id")
                        .value(older.getId().toString()));

        mockMvc.perform(get("/api/forum/posts/{id}", createdId)
                        .header("Authorization", bearer(bob)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content").value("Cooked this tonight."));

        mockMvc.perform(get("/api/forum/posts/mine")
                        .header("Authorization", bearer(alice)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.totalElements").value(1))
                .andExpect(jsonPath("$.content[0].id")
                        .value(createdId.toString()));
    }

    @Test
    void onlyAuthorCanEditAndDeleteAPost() throws Exception {
        UserEntity alice = createUser("alice");
        UserEntity bob = createUser("bob");
        ForumPostEntity post = createPost(alice, null);

        String update = """
                {"title":"Updated dish","content":"Updated notes.","imageId":null}
                """;
        mockMvc.perform(patch("/api/forum/posts/{id}", post.getId())
                        .header("Authorization", bearer(bob))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(update))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("FORUM_POST_NOT_FOUND"));

        mockMvc.perform(delete("/api/forum/posts/{id}", post.getId())
                        .header("Authorization", bearer(bob)))
                .andExpect(status().isNotFound());

        mockMvc.perform(patch("/api/forum/posts/{id}", post.getId())
                        .header("Authorization", bearer(alice))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(update))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Updated dish"))
                .andExpect(jsonPath("$.isOwner").value(true));

        mockMvc.perform(delete("/api/forum/posts/{id}", post.getId())
                        .header("Authorization", bearer(alice)))
                .andExpect(status().isNoContent());
        assertThat(postRepository.existsById(post.getId())).isFalse();
    }

    @Test
    void authorCanAttachOwnImageButNotAnotherUsersImage() throws Exception {
        UserEntity alice = createUser("alice");
        UserEntity bob = createUser("bob");
        UploadedImageEntity ownImage = createImage(alice, "own.jpg");
        UploadedImageEntity bobsImage = createImage(bob, "private.jpg");

        mockMvc.perform(post("/api/forum/posts")
                        .header("Authorization", bearer(alice))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(postJson("Own dish", ownImage.getId())))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.imageId")
                        .value(ownImage.getId().toString()))
                .andExpect(jsonPath("$.imageType").value("USER_UPLOAD"));

        mockMvc.perform(post("/api/forum/posts")
                        .header("Authorization", bearer(alice))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(postJson("Stolen dish", bobsImage.getId())))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("IMAGE_NOT_FOUND"));
        assertThat(postRepository.count()).isEqualTo(1);
    }

    @Test
    void authenticatedViewerCanPreviewOnlyAnImageAttachedToAForumPost() throws Exception {
        UserEntity alice = createUser("alice");
        UserEntity bob = createUser("bob");
        UploadedImageEntity sharedImage = createImage(alice, "shared.jpg");
        UploadedImageEntity privateImage = createImage(alice, "private.jpg");
        ForumPostEntity post = createPost(alice, sharedImage);
        when(objectStorage.exists(sharedImage.getObjectKey())).thenReturn(true);
        when(objectStorage.createReadUrl(sharedImage.getObjectKey())).thenReturn(
                URI.create("https://signed.example/forum-shared")
        );

        mockMvc.perform(get("/api/forum/posts/{id}/image", post.getId())
                        .header("Authorization", bearer(bob)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.imageId")
                        .value(sharedImage.getId().toString()))
                .andExpect(jsonPath("$.url")
                        .value("https://signed.example/forum-shared"));

        mockMvc.perform(get("/api/images/{id}", sharedImage.getId())
                        .header("Authorization", bearer(bob)))
                .andExpect(status().isNotFound());

        mockMvc.perform(get("/api/forum/posts/{id}/image", privateImage.getId())
                        .header("Authorization", bearer(bob)))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("FORUM_POST_NOT_FOUND"));
        verify(objectStorage, never()).createReadUrl(privateImage.getObjectKey());
    }

    @Test
    void forumEndpointsRequireAuthenticationAndValidateContent() throws Exception {
        mockMvc.perform(get("/api/forum/posts"))
                .andExpect(status().isUnauthorized());

        UserEntity alice = createUser("alice");
        mockMvc.perform(post("/api/forum/posts")
                        .header("Authorization", bearer(alice))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\" \",\"content\":\" \"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"));
    }

    @Test
    void ownerGeneratesDraftFromOrderedVisibleHistoryWithPersistedModelAndImage()
            throws Exception {
        UserEntity alice = createUser("alice");
        UploadedImageEntity image = createImage(alice, "cooked.jpg");
        ConversationEntity conversation = createConversation(
                alice,
                ModelId.DEEPSEEK_V4_PRO
        );
        Instant now = Instant.now();
        messageRepository.saveAndFlush(new MessageEntity(
                conversation,
                MessageRole.USER,
                "I have tomatoes and eggs.",
                image,
                now
        ));
        messageRepository.saveAndFlush(new MessageEntity(
                conversation,
                MessageRole.ASSISTANT,
                "Make tomato and egg stir-fry.",
                null,
                now
        ));
        var expectedHistory = List.of(
                new AiCookerClient.DraftMessage(
                        "USER", "I have tomatoes and eggs."
                ),
                new AiCookerClient.DraftMessage(
                        "ASSISTANT", "Make tomato and egg stir-fry."
                )
        );
        when(aiCookerClient.generateForumDraft(
                eq(conversation.getId()),
                eq(expectedHistory),
                eq(ModelId.DEEPSEEK_V4_PRO)
        )).thenReturn(new AiCookerClient.ForumDraftResult(
                "Tomato and Egg Stir-Fry",
                "A quick dish recommended from the conversation.",
                "Tomato and Egg Stir-Fry"
        ));

        mockMvc.perform(post(
                        "/api/forum/drafts/from-conversation/{id}",
                        conversation.getId()
                ).header("Authorization", bearer(alice)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.sourceConversationId")
                        .value(conversation.getId().toString()))
                .andExpect(jsonPath("$.title")
                        .value("Tomato and Egg Stir-Fry"))
                .andExpect(jsonPath("$.suggestedImageId")
                        .value(image.getId().toString()))
                .andExpect(jsonPath("$.suggestedImageType")
                        .value("USER_UPLOAD"))
                .andExpect(jsonPath("$.modelId")
                        .value("DEEPSEEK_V4_PRO"));

        verify(aiCookerClient).generateForumDraft(
                conversation.getId(),
                expectedHistory,
                ModelId.DEEPSEEK_V4_PRO
        );
        verify(aiCookerClient, never()).chat(
                eq(conversation.getId()),
                eq("I have tomatoes and eggs."),
                eq(null),
                eq(ModelId.DEEPSEEK_V4_PRO)
        );
    }

    @Test
    void anotherUsersConversationCannotGenerateDraft() throws Exception {
        UserEntity alice = createUser("alice");
        UserEntity bob = createUser("bob");
        ConversationEntity conversation = createConversation(
                alice,
                ModelId.STEP_FLASH_3_7
        );

        mockMvc.perform(post(
                        "/api/forum/drafts/from-conversation/{id}",
                        conversation.getId()
                ).header("Authorization", bearer(bob)))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code")
                        .value("CONVERSATION_NOT_FOUND"));

        verify(aiCookerClient, never()).generateForumDraft(
                org.mockito.ArgumentMatchers.any(),
                org.mockito.ArgumentMatchers.anyList(),
                org.mockito.ArgumentMatchers.any()
        );
    }

    @Test
    void generatedImageIsSuggestedPublishedAndPubliclyPreviewedWithoutPrivateMetadata()
            throws Exception {
        UserEntity alice = createUser("alice");
        UserEntity bob = createUser("bob");
        ConversationEntity conversation = createConversation(
                alice,
                ModelId.STEP_FLASH_3_7
        );
        Instant now = Instant.now();
        messageRepository.saveAndFlush(new MessageEntity(
                conversation,
                MessageRole.USER,
                "I have tofu and spinach.",
                null,
                now
        ));
        MessageEntity assistant = messageRepository.saveAndFlush(
                new MessageEntity(
                        conversation,
                        MessageRole.ASSISTANT,
                        "Make spinach tofu scramble.",
                        null,
                        now.plusMillis(1)
                )
        );
        GeneratedImageEntity generatedImage = createGeneratedImage(
                alice,
                conversation,
                assistant
        );
        when(aiCookerClient.generateForumDraft(
                eq(conversation.getId()),
                org.mockito.ArgumentMatchers.anyList(),
                eq(ModelId.STEP_FLASH_3_7)
        )).thenReturn(new AiCookerClient.ForumDraftResult(
                "Spinach tofu scramble",
                "A bright and simple tofu scramble.",
                "Spinach tofu scramble"
        ));

        mockMvc.perform(post(
                        "/api/forum/drafts/from-conversation/{id}",
                        conversation.getId()
                ).header("Authorization", bearer(alice)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.suggestedImageId")
                        .value(generatedImage.getId().toString()))
                .andExpect(jsonPath("$.suggestedImageType")
                        .value("AI_GENERATED"))
                .andExpect(jsonPath("$.prompt").doesNotExist())
                .andExpect(jsonPath("$.sourceMessages").doesNotExist());

        String response = mockMvc.perform(post("/api/forum/posts")
                        .header("Authorization", bearer(alice))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "title":"Spinach tofu scramble",
                                  "content":"My edited cooking notes.",
                                  "imageId":"%s",
                                  "imageType":"AI_GENERATED",
                                  "sourceConversationId":"%s"
                                }
                                """.formatted(
                                        generatedImage.getId(),
                                        conversation.getId()
                                )))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.imageId")
                        .value(generatedImage.getId().toString()))
                .andExpect(jsonPath("$.imageType").value("AI_GENERATED"))
                .andReturn().getResponse().getContentAsString();
        UUID postId = UUID.fromString(
                objectMapper.readTree(response).get("id").asText()
        );
        assertThat(postRepository.findById(postId).orElseThrow()
                .getGeneratedImage().getId()).isEqualTo(generatedImage.getId());

        when(objectStorage.exists(generatedImage.getObjectKey())).thenReturn(true);
        when(objectStorage.createReadUrl(generatedImage.getObjectKey()))
                .thenReturn(URI.create("https://signed.example/generated-forum"));
        mockMvc.perform(get("/api/forum/posts/{id}/image", postId)
                        .header("Authorization", bearer(bob)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.imageId")
                        .value(generatedImage.getId().toString()))
                .andExpect(jsonPath("$.url")
                        .value("https://signed.example/generated-forum"))
                .andExpect(jsonPath("$.originalFilename")
                        .value("ai-generated-dish.png"))
                .andExpect(jsonPath("$.prompt").doesNotExist());

        mockMvc.perform(get("/api/generated-images/{id}", generatedImage.getId())
                        .header("Authorization", bearer(bob)))
                .andExpect(status().isNotFound());
    }

    @Test
    void anotherUsersGeneratedImageCannotBePublished() throws Exception {
        UserEntity alice = createUser("alice");
        UserEntity bob = createUser("bob");
        ConversationEntity bobsConversation = createConversation(
                bob,
                ModelId.STEP_FLASH_3_7
        );
        MessageEntity bobsAssistant = messageRepository.saveAndFlush(
                new MessageEntity(
                        bobsConversation,
                        MessageRole.ASSISTANT,
                        "Bob's private recipe.",
                        null,
                        Instant.now()
                )
        );
        GeneratedImageEntity bobsImage = createGeneratedImage(
                bob,
                bobsConversation,
                bobsAssistant
        );

        mockMvc.perform(post("/api/forum/posts")
                        .header("Authorization", bearer(alice))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "title":"Not my image",
                                  "content":"This must be rejected.",
                                  "imageId":"%s",
                                  "imageType":"AI_GENERATED"
                                }
                                """.formatted(bobsImage.getId())))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code")
                        .value("GENERATED_IMAGE_NOT_FOUND"));
        assertThat(postRepository.count()).isZero();
    }

    @Test
    void generatedPublishStoresOwnedSourceButRejectsAnotherUsersSource()
            throws Exception {
        UserEntity alice = createUser("alice");
        UserEntity bob = createUser("bob");
        ConversationEntity conversation = createConversation(
                alice,
                ModelId.STEP_FLASH_3_7
        );

        String publishBody = """
                {
                  "title":"Conversation dish",
                  "content":"Reviewed and edited by the user.",
                  "imageId":null,
                  "sourceConversationId":"%s"
                }
                """.formatted(conversation.getId());
        String response = mockMvc.perform(post("/api/forum/posts")
                        .header("Authorization", bearer(alice))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(publishBody))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString();
        UUID postId = UUID.fromString(
                objectMapper.readTree(response).get("id").asText()
        );
        assertThat(postRepository.findById(postId).orElseThrow()
                .getSourceConversation().getId())
                .isEqualTo(conversation.getId());

        mockMvc.perform(post("/api/forum/posts")
                        .header("Authorization", bearer(bob))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(publishBody))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code")
                        .value("CONVERSATION_NOT_FOUND"));
        assertThat(postRepository.count()).isEqualTo(1);
    }

    private UserEntity createUser(String username) {
        Instant now = Instant.now();
        return userRepository.saveAndFlush(new UserEntity(
                UUID.randomUUID(),
                username,
                passwordEncoder.encode("secure-password"),
                now,
                now
        ));
    }

    private UploadedImageEntity createImage(UserEntity owner, String filename) {
        UUID id = UUID.randomUUID();
        return imageRepository.saveAndFlush(new UploadedImageEntity(
                id,
                owner,
                "users/%s/images/%s.jpg".formatted(owner.getId(), id),
                filename,
                "image/jpeg",
                123L,
                Instant.now()
        ));
    }

    private GeneratedImageEntity createGeneratedImage(
            UserEntity owner,
            ConversationEntity conversation,
            MessageEntity assistantMessage
    ) {
        UUID id = UUID.randomUUID();
        return generatedImageRepository.saveAndFlush(new GeneratedImageEntity(
                id,
                owner,
                conversation,
                assistantMessage,
                "users/%s/generated/%s.png".formatted(owner.getId(), id),
                "step-image-edit-2",
                "private generation prompt",
                "image/png",
                1_024L,
                Instant.now()
        ));
    }

    private ForumPostEntity createPost(
            UserEntity author,
            UploadedImageEntity image
    ) {
        Instant now = Instant.now();
        return postRepository.saveAndFlush(new ForumPostEntity(
                UUID.randomUUID(),
                author,
                "Tomato and egg",
                "Cooked this tonight.",
                image,
                null,
                now,
                now
        ));
    }

    private ConversationEntity createConversation(
            UserEntity owner,
            ModelId modelId
    ) {
        Instant now = Instant.now();
        return conversationRepository.saveAndFlush(new ConversationEntity(
                UUID.randomUUID(),
                owner,
                "Cooking conversation",
                modelId,
                now,
                now
        ));
    }

    private String bearer(UserEntity user) {
        return "Bearer " + jwtService.issue(user.getId(), user.getUsername()).value();
    }

    private static String postJson(String title, UUID imageId) {
        return """
                {"title":"%s","content":"Dinner notes.","imageId":"%s","imageType":"USER_UPLOAD"}
                """.formatted(title, imageId);
    }
}
