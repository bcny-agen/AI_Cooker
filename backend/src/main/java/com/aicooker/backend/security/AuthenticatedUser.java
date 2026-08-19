package com.aicooker.backend.security;

import java.security.Principal;
import java.util.UUID;

public final class AuthenticatedUser {

    private AuthenticatedUser() {
    }

    public static UUID id(Principal principal) {
        if (principal == null) {
            throw new IllegalStateException("Authenticated principal is missing.");
        }
        return UUID.fromString(principal.getName());
    }
}
