package com.aicooker.backend.controller;

import java.security.Principal;
import java.util.UUID;

import com.aicooker.backend.dto.CreateForumPostRequest;
import com.aicooker.backend.dto.ForumPostResponse;
import com.aicooker.backend.dto.ImageResponse;
import com.aicooker.backend.dto.PageResponse;
import com.aicooker.backend.dto.UpdateForumPostRequest;
import com.aicooker.backend.security.AuthenticatedUser;
import com.aicooker.backend.service.ForumImageService;
import com.aicooker.backend.service.ForumPostService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.http.HttpStatus;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@Validated
@RestController
@RequestMapping("/api/forum/posts")
public class ForumController {

    private final ForumPostService postService;
    private final ForumImageService imageService;

    public ForumController(
            ForumPostService postService,
            ForumImageService imageService
    ) {
        this.postService = postService;
        this.imageService = imageService;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public ForumPostResponse create(
            Principal principal,
            @Valid @RequestBody CreateForumPostRequest request
    ) {
        return postService.create(AuthenticatedUser.id(principal), request);
    }

    @GetMapping
    public PageResponse<ForumPostResponse> list(
            Principal principal,
            @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "12") @Min(1) @Max(50) int size
    ) {
        return postService.list(AuthenticatedUser.id(principal), page, size);
    }

    @GetMapping("/mine")
    public PageResponse<ForumPostResponse> listMine(
            Principal principal,
            @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "12") @Min(1) @Max(50) int size
    ) {
        return postService.listMine(AuthenticatedUser.id(principal), page, size);
    }

    @GetMapping("/{postId}")
    public ForumPostResponse get(
            Principal principal,
            @PathVariable UUID postId
    ) {
        return postService.get(AuthenticatedUser.id(principal), postId);
    }

    @GetMapping("/{postId}/image")
    public ImageResponse image(
            Principal principal,
            @PathVariable UUID postId
    ) {
        AuthenticatedUser.id(principal);
        return imageService.createPreview(postId);
    }

    @PatchMapping("/{postId}")
    public ForumPostResponse update(
            Principal principal,
            @PathVariable UUID postId,
            @Valid @RequestBody UpdateForumPostRequest request
    ) {
        return postService.update(
                AuthenticatedUser.id(principal),
                postId,
                request
        );
    }

    @DeleteMapping("/{postId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(
            Principal principal,
            @PathVariable UUID postId
    ) {
        postService.delete(AuthenticatedUser.id(principal), postId);
    }
}
