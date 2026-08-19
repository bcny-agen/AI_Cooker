package com.aicooker.backend.exception;

import com.aicooker.backend.entity.ModelId;

public class ModelUnavailableException extends RuntimeException {

    public ModelUnavailableException(ModelId modelId) {
        super("Model is not available: " + modelId);
    }
}
