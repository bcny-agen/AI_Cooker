package com.aicooker.backend.service;

import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Instant;
import java.util.Locale;
import java.util.UUID;

import com.aicooker.backend.dto.LoginRequest;
import com.aicooker.backend.dto.LoginResponse;
import com.aicooker.backend.dto.RegisterRequest;
import com.aicooker.backend.dto.UserResponse;
import com.aicooker.backend.entity.UserEntity;
import com.aicooker.backend.exception.InvalidLoginException;
import com.aicooker.backend.exception.PasswordTooLongException;
import com.aicooker.backend.exception.UsernameAlreadyExistsException;
import com.aicooker.backend.repository.UserRepository;
import com.aicooker.backend.security.JwtService;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuthService {

    private static final String LEGACY_USERNAME = "__legacy_history_owner__";

    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;
    private final JwtService jwtService;
    private final Clock clock;
    private final String dummyPasswordHash;

    public AuthService(
            UserRepository userRepository,
            PasswordEncoder passwordEncoder,
            JwtService jwtService,
            Clock clock
    ) {
        this.userRepository = userRepository;
        this.passwordEncoder = passwordEncoder;
        this.jwtService = jwtService;
        this.clock = clock;
        this.dummyPasswordHash = passwordEncoder.encode(
                "dummy-login-check-" + UUID.randomUUID()
        );
    }

    @Transactional
    public UserResponse register(RegisterRequest request) {
        String username = normalize(request.username());
        if (utf8Length(request.password()) > 72) {
            throw new PasswordTooLongException();
        }
        if (LEGACY_USERNAME.equals(username)
                || userRepository.existsByUsername(username)) {
            throw new UsernameAlreadyExistsException();
        }

        Instant now = clock.instant();
        UserEntity user = new UserEntity(
                UUID.randomUUID(),
                username,
                passwordEncoder.encode(request.password()),
                now,
                now
        );

        try {
            userRepository.saveAndFlush(user);
        } catch (DataIntegrityViolationException exception) {
            throw new UsernameAlreadyExistsException();
        }

        return new UserResponse(user.getId(), user.getUsername(), user.getCreatedAt());
    }

    @Transactional(readOnly = true)
    public LoginResponse login(LoginRequest request) {
        String username = normalize(request.username());
        UserEntity user = LEGACY_USERNAME.equals(username)
                ? null
                : userRepository.findByUsername(username).orElse(null);
        String passwordHash = user == null
                ? dummyPasswordHash
                : user.getPasswordHash();
        boolean passwordMatches = utf8Length(request.password()) <= 72
                && passwordEncoder.matches(request.password(), passwordHash);
        if (user == null || !passwordMatches) {
            throw new InvalidLoginException();
        }

        JwtService.IssuedToken token = jwtService.issue(
                user.getId(),
                user.getUsername()
        );
        return new LoginResponse(token.value(), token.expiresIn());
    }

    private static String normalize(String username) {
        return username.trim().toLowerCase(Locale.ROOT);
    }

    private static int utf8Length(String value) {
        return value.getBytes(StandardCharsets.UTF_8).length;
    }
}
