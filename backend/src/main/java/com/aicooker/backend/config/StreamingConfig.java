package com.aicooker.backend.config;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class StreamingConfig {

    @Bean(name = "aiStreamExecutor", destroyMethod = "close")
    ExecutorService aiStreamExecutor() {
        var threadFactory = Thread.ofVirtual()
                .name("ai-cooker-stream-", 0)
                .factory();
        return Executors.newThreadPerTaskExecutor(threadFactory);
    }
}
