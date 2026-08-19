package com.aicooker.backend.exception;

import java.util.Objects;

import org.springframework.dao.DataAccessException;

public class BusinessStorageOperationException extends RuntimeException {

    private final String operation;

    public BusinessStorageOperationException(
            String operation,
            DataAccessException cause
    ) {
        super("Business storage operation failed.", cause);
        this.operation = Objects.requireNonNull(operation);
    }

    public String getOperation() {
        return operation;
    }
}
