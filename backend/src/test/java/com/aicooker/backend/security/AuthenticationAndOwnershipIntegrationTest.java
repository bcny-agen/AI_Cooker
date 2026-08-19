package com.aicooker.backend.security;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.reset;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.net.URI;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

import com.aicooker.backend.client.AiCookerClient;
import com.aicooker.backend.entity.ForumPostEntity;
import com.aicooker.backend.entity.UserEntity;
import com.aicooker.backend.entity.UploadedImageEntity;
import com.aicooker.backend.entity.ModelId;
import com.aicooker.backend.exception.AiThreadRecoveryRequiredException;
import com.aicooker.backend.repository.ConversationRepository;
import com.aicooker.backend.repository.ForumPostRepository;
import com.aicooker.backend.repository.GeneratedImageRepository;
import com.aicooker.backend.repository.MessageRepository;
import com.aicooker.backend.repository.UserRepository;
import com.aicooker.backend.repository.UploadedImageRepository;
import com.aicooker.backend.service.ConversationPersistenceService;
import com.aicooker.backend.storage.ImageObjectStorage;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class AuthenticationAndOwnershipIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private ConversationRepository conversationRepository;

    @Autowired
    private ForumPostRepository forumPostRepository;

    @Autowired
    private GeneratedImageRepository generatedImageRepository;

    @Autowired
    private MessageRepository messageRepository;

    @Autowired
    private UploadedImageRepository imageRepository;

    @Autowired
    private ConversationPersistenceService persistenceService;

    @Autowired
    private PasswordEncoder passwordEncoder;

    @Autowired
    private JwtDecoder jwtDecoder;

    @Autowired
    private JwtService jwtService;

    @MockitoBean
    private AiCookerClient aiCookerClient;

    @MockitoBean
    private ImageObjectStorage imageObjectStorage;

    @BeforeEach
    void cleanDatabase() {
        forumPostRepository.deleteAllInBatch();
        generatedImageRepository.deleteAllInBatch();
        messageRepository.deleteAllInBatch();
        conversationRepository.deleteAllInBatch();
        imageRepository.deleteAllInBatch();
        userRepository.deleteAllInBatch();
        reset(aiCookerClient, imageObjectStorage);
        when(aiCookerClient.listModels()).thenReturn(List.of(
                new AiCookerClient.ModelDescriptor(
                        ModelId.STEP_FLASH_3_7,
                        "Step 3.7 Flash",
                        true,
                        true,
                        true,
                        true,
                        true
                ),
                new AiCookerClient.ModelDescriptor(
                        ModelId.DEEPSEEK_V4_PRO,
                        "DeepSeek V4 Pro",
                        true,
                        true,
                        true,
                        false,
                        true
                )
        ));
    }

    @Test
    void registrationStoresAHashInsteadOfThePassword() throws Exception {
        mockMvc.perform(post("/api/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "username": "Alice",
                                  "password": "correct-horse-battery-staple"
                                }
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.username").value("alice"));

        UserEntity stored = userRepository.findByUsername("alice").orElseThrow();
        assertThat(stored.getPasswordHash())
                .isNotEqualTo("correct-horse-battery-staple")
                .startsWith("$2");
        assertThat(passwordEncoder.matches(
                "correct-horse-battery-staple",
                stored.getPasswordHash()
        )).isTrue();
    }

    @Test
    void loginReturnsAValidSignedJwt() throws Exception {
        UserEntity user = createUser("alice", "secure-password");

        String responseBody = mockMvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "username": "ALICE",
                                  "password": "secure-password"
                                }
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.token").isString())
                .andExpect(jsonPath("$.expiresIn").value(3600))
                .andReturn()
                .getResponse()
                .getContentAsString();

        String token = objectMapper.readTree(responseBody).get("token").asText();
        var decoded = jwtDecoder.decode(token);
        assertThat(decoded.getSubject()).isEqualTo(user.getId().toString());
        assertThat(decoded.getClaimAsString("username")).isEqualTo("alice");
    }

    @Test
    void invalidLoginDoesNotRevealWhetherTheUsernameExists() throws Exception {
        createUser("alice", "secure-password");

        mockMvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "username": "alice",
                                  "password": "wrong-password"
                                }
                                """))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("INVALID_CREDENTIALS"))
                .andExpect(jsonPath("$.message")
                        .value("Invalid username or password."));
    }

    @Test
    void protectedApisRejectMissingAndTamperedTokens() throws Exception {
        mockMvc.perform(get("/api/conversations"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("UNAUTHORIZED"));

        mockMvc.perform(post("/api/chat/stream")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"message":"I have eggs"}
                                """))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("UNAUTHORIZED"));

        UserEntity user = createUser("alice", "secure-password");
        String validToken = tokenFor(user);
        int signatureStart = validToken.lastIndexOf('.') + 1;
        char firstSignatureCharacter = validToken.charAt(signatureStart);
        String tamperedToken = validToken.substring(0, signatureStart)
                + (firstSignatureCharacter == 'a' ? 'b' : 'a')
                + validToken.substring(signatureStart + 1);

        mockMvc.perform(get("/api/conversations")
                        .header("Authorization", "Bearer " + tamperedToken))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("UNAUTHORIZED"));
    }

    @Test
    void allowsConfiguredViteDevelopmentOriginOnly() throws Exception {
        mockMvc.perform(options("/api/chat")
                        .header("Origin", "http://localhost:5173")
                        .header("Access-Control-Request-Method", "POST")
                        .header(
                                "Access-Control-Request-Headers",
                                "authorization,content-type"
                        ))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "Access-Control-Allow-Origin",
                        "http://localhost:5173"
                ));

        mockMvc.perform(options("/api/chat")
                        .header("Origin", "https://untrusted.example")
                        .header("Access-Control-Request-Method", "POST"))
                .andExpect(status().isForbidden())
                .andExpect(header().doesNotExist("Access-Control-Allow-Origin"));
    }

    @Test
    void userCannotReadOrContinueAnotherUsersConversation() throws Exception {
        UserEntity alice = createUser("alice", "secure-password");
        UserEntity bob = createUser("bob", "secure-password");
        UUID bobsConversation = UUID.randomUUID();
        persistenceService.recordUserMessage(
                bob.getId(),
                bobsConversation,
                "Bob's private recipe",
                null
        );

        String aliceToken = tokenFor(alice);
        mockMvc.perform(get("/api/conversations/{id}", bobsConversation)
                        .header("Authorization", "Bearer " + aliceToken))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("CONVERSATION_NOT_FOUND"));

        mockMvc.perform(get(
                        "/api/conversations/{id}/messages",
                        bobsConversation
                ).header("Authorization", "Bearer " + aliceToken))
                .andExpect(status().isNotFound());

        mockMvc.perform(post("/api/chat")
                        .header("Authorization", "Bearer " + aliceToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "conversationId": "%s",
                                  "message": "Try to continue Bob's chat"
                                }
                                """.formatted(bobsConversation)))
                .andExpect(status().isNotFound());

        mockMvc.perform(post("/api/chat/stream")
                        .header("Authorization", "Bearer " + aliceToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "conversationId": "%s",
                                  "message": "Try to stream Bob's chat"
                                }
                                """.formatted(bobsConversation)))
                .andExpect(status().isNotFound());

        verify(aiCookerClient, never()).chat(
                eq(bobsConversation),
                any(String.class),
                any(),
                any(),
                any()
        );
        verify(aiCookerClient, never()).streamChat(
                eq(bobsConversation),
                any(String.class),
                any(),
                any(),
                any(),
                any()
        );
    }

    @Test
    void authenticatedChatCreatesConversationForTheCorrectUser() throws Exception {
        UserEntity alice = createUser("alice", "secure-password");
        when(aiCookerClient.chat(
                any(UUID.class),
                eq("I have eggs"),
                isNull(),
                eq(ModelId.STEP_FLASH_3_7),
                eq(java.util.List.of()),
                eq(false)
        )).thenAnswer(invocation -> new AiCookerClient.ChatResult(
                invocation.getArgument(0),
                "Make an omelette"
        ));

        String responseBody = mockMvc.perform(post("/api/chat")
                        .header("Authorization", "Bearer " + tokenFor(alice))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "message": "I have eggs",
                                  "imageId": null
                                }
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.answer").value("Make an omelette"))
                .andReturn()
                .getResponse()
                .getContentAsString();

        JsonNode response = objectMapper.readTree(responseBody);
        UUID conversationId = UUID.fromString(
                response.get("conversationId").asText()
        );
        assertThat(conversationRepository.findByIdAndUser_Id(
                conversationId,
                alice.getId()
        )).isPresent();
        assertThat(messageRepository.findByConversation_Id(
                conversationId,
                org.springframework.data.domain.Pageable.unpaged()
        ).getContent()).hasSize(2);
    }

    @Test
    void legacyConversationRecoversAndPersistsBothVisibleMessages() throws Exception {
        UserEntity alice = createUser("alice-legacy", "secure-password");
        UUID conversationId = UUID.randomUUID();
        persistenceService.recordUserMessage(
                alice.getId(), conversationId, "Earlier ingredient question", null
        );
        persistenceService.recordAssistantMessage(
                alice.getId(), conversationId, "Earlier recipe answer"
        );

        when(aiCookerClient.chat(
                eq(conversationId),
                eq("Can I make it less oily?"),
                isNull(),
                eq(ModelId.STEP_FLASH_3_7),
                eq(List.of()),
                eq(true)
        )).thenThrow(new AiThreadRecoveryRequiredException(
                new IllegalStateException("missing legacy checkpoint")
        ));
        when(aiCookerClient.recoverChat(
                eq(conversationId),
                eq("Can I make it less oily?"),
                isNull(),
                eq(ModelId.STEP_FLASH_3_7),
                eq(List.of()),
                any()
        )).thenReturn(new AiCookerClient.ChatResult(
                conversationId,
                "Use less oil and add a splash of water."
        ));

        mockMvc.perform(post("/api/chat")
                        .header("Authorization", "Bearer " + tokenFor(alice))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "conversationId": "%s",
                                  "message": "Can I make it less oily?"
                                }
                                """.formatted(conversationId)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.conversationId")
                        .value(conversationId.toString()));

        var afterRecovery = messageRepository
                .findByConversation_IdOrderByCreatedAtAscIdAsc(conversationId);
        assertThat(afterRecovery).extracting(message -> message.getRole())
                .containsExactly(
                        com.aicooker.backend.entity.MessageRole.USER,
                        com.aicooker.backend.entity.MessageRole.ASSISTANT,
                        com.aicooker.backend.entity.MessageRole.USER,
                        com.aicooker.backend.entity.MessageRole.ASSISTANT
                );
        assertThat(afterRecovery.get(2).getContent())
                .isEqualTo("Can I make it less oily?");
        assertThat(afterRecovery.get(3).getContent())
                .isEqualTo("Use less oil and add a splash of water.");

        when(aiCookerClient.chat(
                eq(conversationId),
                eq("What should I serve with it?"),
                isNull(),
                eq(ModelId.STEP_FLASH_3_7),
                eq(List.of()),
                eq(true)
        )).thenReturn(new AiCookerClient.ChatResult(
                conversationId,
                "Serve it with rice."
        ));

        mockMvc.perform(post("/api/chat")
                        .header("Authorization", "Bearer " + tokenFor(alice))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "conversationId": "%s",
                                  "message": "What should I serve with it?"
                                }
                                """.formatted(conversationId)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.conversationId")
                        .value(conversationId.toString()));

        assertThat(messageRepository
                .findByConversation_IdOrderByCreatedAtAscIdAsc(conversationId))
                .hasSize(6);
        verify(aiCookerClient, times(1)).recoverChat(
                eq(conversationId), any(), any(), any(), any(), any()
        );
    }

    @Test
    void onlyOwnerCanSwitchConversationModel() throws Exception {
        UserEntity alice = createUser("alice", "secure-password");
        UserEntity bob = createUser("bob", "secure-password");
        UUID conversationId = UUID.randomUUID();
        persistenceService.recordUserMessage(
                alice.getId(), conversationId, "first", null
        );

        mockMvc.perform(patch(
                        "/api/conversations/{id}/model",
                        conversationId
                ).header("Authorization", "Bearer " + tokenFor(bob))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"modelId\":\"DEEPSEEK_V4_PRO\"}"))
                .andExpect(status().isNotFound());

        mockMvc.perform(patch(
                        "/api/conversations/{id}/model",
                        conversationId
                ).header("Authorization", "Bearer " + tokenFor(alice))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"modelId\":\"DEEPSEEK_V4_PRO\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.modelId").value("DEEPSEEK_V4_PRO"));

        assertThat(conversationRepository.findById(conversationId).orElseThrow()
                .getSelectedModel()).isEqualTo(ModelId.DEEPSEEK_V4_PRO);
    }

    @Test
    void onlyOwnerCanRenameAndDeleteConversation() throws Exception {
        UserEntity alice = createUser("alice-management", "secure-password");
        UserEntity bob = createUser("bob-management", "secure-password");
        UUID conversationId = UUID.randomUUID();
        UploadedImageEntity image = createImage(alice);
        persistenceService.recordUserMessage(
                alice.getId(), conversationId, "first", image.getId()
        );
        persistenceService.recordAssistantMessage(
                alice.getId(), conversationId, "first answer"
        );
        persistenceService.recordUserMessage(
                alice.getId(), conversationId, "legacy follow-up", null
        );
        persistenceService.recordAssistantMessage(
                alice.getId(), conversationId, "second answer"
        );
        UUID forumPostId = UUID.randomUUID();
        Instant now = Instant.now();
        forumPostRepository.saveAndFlush(new ForumPostEntity(
                forumPostId,
                alice,
                "Published recipe",
                "Public content remains after chat deletion.",
                image,
                conversationRepository.findById(conversationId).orElseThrow(),
                now,
                now
        ));

        mockMvc.perform(patch("/api/conversations/{id}", conversationId)
                        .header("Authorization", "Bearer " + tokenFor(bob))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"Bob cannot rename this\"}"))
                .andExpect(status().isNotFound());

        mockMvc.perform(patch("/api/conversations/{id}", conversationId)
                        .header("Authorization", "Bearer " + tokenFor(alice))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"Alice's dinner\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(conversationId.toString()))
                .andExpect(jsonPath("$.title").value("Alice's dinner"));

        mockMvc.perform(delete("/api/conversations/{id}", conversationId)
                        .header("Authorization", "Bearer " + tokenFor(bob)))
                .andExpect(status().isNotFound());
        verify(aiCookerClient, never()).deleteConversationState(conversationId);

        mockMvc.perform(delete("/api/conversations/{id}", conversationId)
                        .header("Authorization", "Bearer " + tokenFor(alice)))
                .andExpect(status().isNoContent());

        verify(aiCookerClient).deleteConversationState(conversationId);
        assertThat(conversationRepository.findById(conversationId)).isEmpty();
        assertThat(messageRepository.findByConversation_Id(
                conversationId,
                org.springframework.data.domain.Pageable.unpaged()
        ).getContent()).isEmpty();
        assertThat(imageRepository.findById(image.getId())).isPresent();
        var remainingPost = forumPostRepository.findById(forumPostId)
                .orElseThrow();
        assertThat(remainingPost.getSourceConversation()).isNull();
        assertThat(remainingPost.getImage().getId()).isEqualTo(image.getId());
    }

    @Test
    void authenticatedUserCanUploadValidImageMetadata() throws Exception {
        UserEntity alice = createUser("alice", "secure-password");
        when(imageObjectStorage.createReadUrl(any(String.class))).thenReturn(
                URI.create("https://signed.example/uploaded-image")
        );
        var file = new MockMultipartFile(
                "file",
                "ingredients.jpg",
                "image/jpeg",
                new byte[]{(byte) 0xFF, (byte) 0xD8, (byte) 0xFF, 0x01}
        );

        mockMvc.perform(multipart("/api/images")
                        .file(file)
                        .header("Authorization", "Bearer " + tokenFor(alice)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.imageId").isString())
                .andExpect(jsonPath("$.url")
                        .value("https://signed.example/uploaded-image"))
                .andExpect(jsonPath("$.originalFilename")
                        .value("ingredients.jpg"))
                .andExpect(jsonPath("$.contentType").value("image/jpeg"))
                .andExpect(jsonPath("$.size").value(4));

        assertThat(imageRepository.count()).isEqualTo(1);
        UploadedImageEntity stored = imageRepository.findAll().getFirst();
        assertThat(stored.getUser().getId()).isEqualTo(alice.getId());
        assertThat(stored.getObjectKey())
                .startsWith("users/" + alice.getId() + "/images/");
        when(imageObjectStorage.exists(stored.getObjectKey())).thenReturn(true);

        mockMvc.perform(get("/api/images/{imageId}", stored.getId())
                        .header("Authorization", "Bearer " + tokenFor(alice)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.imageId").value(stored.getId().toString()))
                .andExpect(jsonPath("$.url")
                        .value("https://signed.example/uploaded-image"));
    }

    @Test
    void anotherUserCannotUseImageInChat() throws Exception {
        UserEntity alice = createUser("alice", "secure-password");
        UserEntity bob = createUser("bob", "secure-password");
        UploadedImageEntity bobsImage = createImage(bob);

        mockMvc.perform(get("/api/images/{imageId}", bobsImage.getId())
                        .header("Authorization", "Bearer " + tokenFor(alice)))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("IMAGE_NOT_FOUND"));

        mockMvc.perform(post("/api/chat")
                        .header("Authorization", "Bearer " + tokenFor(alice))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "message": "Use Bob's image",
                                  "imageId": "%s"
                                }
                                """.formatted(bobsImage.getId())))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("IMAGE_NOT_FOUND"));

        verify(imageObjectStorage, never()).createReadUrl(any(String.class));
        verify(aiCookerClient, never()).chat(
                any(), any(), any(), any(), any()
        );
    }

    @Test
    void chatMapsImageIdToSignedUrlAndPersistsImageReference() throws Exception {
        UserEntity alice = createUser("alice", "secure-password");
        UploadedImageEntity image = createImage(alice);
        when(imageObjectStorage.exists(image.getObjectKey())).thenReturn(true);
        when(imageObjectStorage.createReadUrl(image.getObjectKey())).thenReturn(
                URI.create("https://signed.example/fresh-agent-url")
        );
        when(aiCookerClient.chat(
                any(UUID.class),
                eq("What can I cook?"),
                eq("https://signed.example/fresh-agent-url"),
                eq(ModelId.STEP_FLASH_3_7),
                eq(java.util.List.of()),
                eq(false)
        )).thenAnswer(invocation -> new AiCookerClient.ChatResult(
                invocation.getArgument(0),
                "You can make soup."
        ));

        String responseBody = mockMvc.perform(post("/api/chat")
                        .header("Authorization", "Bearer " + tokenFor(alice))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "message": "What can I cook?",
                                  "imageId": "%s"
                                }
                                """.formatted(image.getId())))
                .andExpect(status().isOk())
                .andReturn()
                .getResponse()
                .getContentAsString();

        UUID conversationId = UUID.fromString(
                objectMapper.readTree(responseBody).get("conversationId").asText()
        );
        mockMvc.perform(get(
                        "/api/conversations/{id}/messages",
                        conversationId
                ).header("Authorization", "Bearer " + tokenFor(alice)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content[0].imageId")
                        .value(image.getId().toString()))
                .andExpect(jsonPath("$.content[1].imageId").isEmpty());

        verify(aiCookerClient).chat(
                eq(conversationId),
                eq("What can I cook?"),
                eq("https://signed.example/fresh-agent-url"),
                eq(ModelId.STEP_FLASH_3_7),
                eq(java.util.List.of()),
                eq(false)
        );
    }

    private UserEntity createUser(String username, String password) {
        Instant now = Instant.now();
        return userRepository.saveAndFlush(new UserEntity(
                UUID.randomUUID(),
                username,
                passwordEncoder.encode(password),
                now,
                now
        ));
    }

    private String tokenFor(UserEntity user) {
        return jwtService.issue(user.getId(), user.getUsername()).value();
    }

    private UploadedImageEntity createImage(UserEntity owner) {
        UUID imageId = UUID.randomUUID();
        return imageRepository.saveAndFlush(new UploadedImageEntity(
                imageId,
                owner,
                "users/%s/images/%s.jpg".formatted(owner.getId(), imageId),
                "ingredients.jpg",
                "image/jpeg",
                123L,
                Instant.now()
        ));
    }
}
