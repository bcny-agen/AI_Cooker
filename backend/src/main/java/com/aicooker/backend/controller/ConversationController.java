package com.aicooker.backend.controller;

import java.security.Principal;
import java.util.UUID;

import com.aicooker.backend.dto.ConversationResponse;
import com.aicooker.backend.dto.ChangeConversationModelRequest;
import com.aicooker.backend.dto.MessageResponse;
import com.aicooker.backend.dto.PageResponse;
import com.aicooker.backend.dto.RenameConversationRequest;
import com.aicooker.backend.security.AuthenticatedUser;
import com.aicooker.backend.service.ConversationQueryService;
import com.aicooker.backend.service.ConversationModelService;
import com.aicooker.backend.service.ConversationManagementService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.http.ResponseEntity;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

@Validated
@RestController
@RequestMapping("/api/conversations")
public class ConversationController {

    private static final Logger LOGGER = LoggerFactory.getLogger(
            ConversationController.class
    );

    private final ConversationQueryService conversationQueryService;
    private final ConversationModelService conversationModelService;
    private final ConversationManagementService conversationManagementService;

    public ConversationController(
            ConversationQueryService conversationQueryService,
            ConversationModelService conversationModelService,
            ConversationManagementService conversationManagementService
    ) {
        this.conversationQueryService = conversationQueryService;
        this.conversationModelService = conversationModelService;
        this.conversationManagementService = conversationManagementService;
    }

    @PatchMapping("/{conversationId}")
    public ConversationResponse renameConversation(
            Principal principal,
            @PathVariable UUID conversationId,
            @Valid @RequestBody RenameConversationRequest request
    ) {
        return conversationManagementService.rename(
                AuthenticatedUser.id(principal),
                conversationId,
                request.title()
        );
    }

    @DeleteMapping("/{conversationId}")
    public ResponseEntity<Void> deleteConversation(
            Principal principal,
            @PathVariable UUID conversationId
    ) {
        LOGGER.info(
                "conversation_delete operation=REQUEST_RECEIVED "
                        + "conversationId={}",
                conversationId
        );
        conversationManagementService.delete(
                AuthenticatedUser.id(principal),
                conversationId
        );
        LOGGER.info(
                "conversation_delete operation=REQUEST_COMPLETED "
                        + "conversationId={}",
                conversationId
        );
        return ResponseEntity.noContent().build();
    }

    @PatchMapping("/{conversationId}/model")
    public ConversationResponse changeModel(
            Principal principal,
            @PathVariable UUID conversationId,
            @Valid @RequestBody ChangeConversationModelRequest request
    ) {
        return conversationModelService.changeModel(
                AuthenticatedUser.id(principal),
                conversationId,
                request.modelId()
        );
    }

    @GetMapping
    public PageResponse<ConversationResponse> listConversations(
            Principal principal,
            @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size
    ) {
        return conversationQueryService.listConversations(
                AuthenticatedUser.id(principal),
                page,
                size
        );
    }

    @GetMapping("/{conversationId}")
    public ConversationResponse getConversation(
            Principal principal,
            @PathVariable UUID conversationId
    ) {
        return conversationQueryService.getConversation(
                AuthenticatedUser.id(principal),
                conversationId
        );
    }

    @GetMapping("/{conversationId}/messages")
    public PageResponse<MessageResponse> listMessages(
            Principal principal,
            @PathVariable UUID conversationId,
            @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "50") @Min(1) @Max(100) int size
    ) {
        return conversationQueryService.listMessages(
                AuthenticatedUser.id(principal),
                conversationId,
                page,
                size
        );
    }
}
