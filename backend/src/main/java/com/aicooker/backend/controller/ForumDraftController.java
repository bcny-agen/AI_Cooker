package com.aicooker.backend.controller;

import java.security.Principal;
import java.util.UUID;

import com.aicooker.backend.dto.ForumDraftResponse;
import com.aicooker.backend.security.AuthenticatedUser;
import com.aicooker.backend.service.ForumDraftService;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/forum/drafts")
public class ForumDraftController {

    private final ForumDraftService draftService;

    public ForumDraftController(ForumDraftService draftService) {
        this.draftService = draftService;
    }

    @PostMapping("/from-conversation/{conversationId}")
    public ForumDraftResponse generateFromConversation(
            Principal principal,
            @PathVariable UUID conversationId
    ) {
        return draftService.generate(
                AuthenticatedUser.id(principal),
                conversationId
        );
    }
}
