package com.aicooker.backend.controller;

import java.security.Principal;
import java.util.concurrent.Executor;
import java.util.concurrent.atomic.AtomicBoolean;

import com.aicooker.backend.dto.ChatRequest;
import com.aicooker.backend.dto.ChatResponse;
import com.aicooker.backend.dto.ChatStreamEvent;
import com.aicooker.backend.security.AuthenticatedUser;
import com.aicooker.backend.service.ChatService;
import jakarta.validation.Valid;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@RestController
@RequestMapping("/api")
public class ChatController {

    private final ChatService chatService;
    private final Executor streamExecutor;

    public ChatController(
            ChatService chatService,
            @Qualifier("aiStreamExecutor") Executor streamExecutor
    ) {
        this.chatService = chatService;
        this.streamExecutor = streamExecutor;
    }

    @PostMapping("/chat")
    public ChatResponse chat(
            Principal principal,
            @Valid @RequestBody ChatRequest request
    ) {
        return chatService.chat(AuthenticatedUser.id(principal), request);
    }

    @PostMapping(
            value = "/chat/stream",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    public SseEmitter streamChat(
            Principal principal,
            @Valid @RequestBody ChatRequest request
    ) {
        ChatService.StreamSession session = chatService.beginStream(
                AuthenticatedUser.id(principal),
                request
        );
        var emitter = new SseEmitter(0L);
        var closed = new AtomicBoolean(false);

        emitter.onCompletion(() -> closed.set(true));
        emitter.onError(error -> closed.set(true));
        emitter.onTimeout(() -> {
            closed.set(true);
            emitter.complete();
        });

        streamExecutor.execute(() -> {
            try {
                chatService.stream(
                        session,
                        event -> send(emitter, closed, event)
                );
            } catch (ClientStreamClosedException ignored) {
                // The browser disconnected; closing the upstream response stops reads.
            } catch (Exception exception) {
                if (!closed.get()) {
                    try {
                        send(
                                emitter,
                                closed,
                                ChatStreamEvent.error(session.conversationId())
                        );
                    } catch (ClientStreamClosedException ignored) {
                        // The client went away while the failure was being reported.
                    }
                }
            } finally {
                if (closed.compareAndSet(false, true)) {
                    emitter.complete();
                }
            }
        });

        return emitter;
    }

    private static void send(
            SseEmitter emitter,
            AtomicBoolean closed,
            ChatStreamEvent event
    ) {
        if (closed.get()) {
            throw new ClientStreamClosedException();
        }
        try {
            emitter.send(SseEmitter.event()
                    .name(event.type())
                    .data(event, MediaType.APPLICATION_JSON));
        } catch (Exception exception) {
            closed.set(true);
            throw new ClientStreamClosedException(exception);
        }
    }

    private static final class ClientStreamClosedException
            extends RuntimeException {

        private ClientStreamClosedException() {
            super();
        }

        private ClientStreamClosedException(Throwable cause) {
            super(cause);
        }
    }
}
