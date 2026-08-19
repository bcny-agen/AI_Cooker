package com.aicooker.backend.controller;

import java.security.Principal;
import java.util.List;
import java.util.UUID;

import com.aicooker.backend.dto.MemoryResponse;
import com.aicooker.backend.dto.UpdateMemoryRequest;
import com.aicooker.backend.security.AuthenticatedUser;
import com.aicooker.backend.service.UserMemoryService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/memories")
public class MemoryController {

    private final UserMemoryService userMemoryService;

    public MemoryController(UserMemoryService userMemoryService) {
        this.userMemoryService = userMemoryService;
    }

    @GetMapping
    public List<MemoryResponse> list(Principal principal) {
        return userMemoryService.list(AuthenticatedUser.id(principal));
    }

    @PatchMapping("/{memoryId}")
    public MemoryResponse update(
            Principal principal,
            @PathVariable UUID memoryId,
            @Valid @RequestBody UpdateMemoryRequest request
    ) {
        return userMemoryService.update(
                AuthenticatedUser.id(principal),
                memoryId,
                request
        );
    }

    @DeleteMapping("/{memoryId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(
            Principal principal,
            @PathVariable UUID memoryId
    ) {
        userMemoryService.delete(AuthenticatedUser.id(principal), memoryId);
    }
}
