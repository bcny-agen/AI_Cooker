package com.aicooker.backend.controller;

import java.security.Principal;

import com.aicooker.backend.dto.ImageResponse;
import com.aicooker.backend.security.AuthenticatedUser;
import com.aicooker.backend.service.ImageService;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/images")
public class ImageController {

    private final ImageService imageService;

    public ImageController(ImageService imageService) {
        this.imageService = imageService;
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    @ResponseStatus(HttpStatus.CREATED)
    public ImageResponse upload(
            Principal principal,
            @RequestParam("file") MultipartFile file
    ) {
        return imageService.upload(AuthenticatedUser.id(principal), file);
    }

    @GetMapping("/{imageId}")
    public ImageResponse getImage(
            Principal principal,
            @PathVariable java.util.UUID imageId
    ) {
        return imageService.getImage(AuthenticatedUser.id(principal), imageId);
    }
}
