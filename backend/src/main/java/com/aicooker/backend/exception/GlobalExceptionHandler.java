package com.aicooker.backend.exception;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.ConstraintViolationException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.multipart.MaxUploadSizeExceededException;
import org.springframework.web.multipart.support.MissingServletRequestPartException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger LOGGER = LoggerFactory.getLogger(
            GlobalExceptionHandler.class
    );

    @ExceptionHandler({
            MethodArgumentNotValidException.class,
            HttpMessageNotReadableException.class,
            ConstraintViolationException.class,
            HandlerMethodValidationException.class,
            MethodArgumentTypeMismatchException.class,
            MissingServletRequestParameterException.class,
            MissingServletRequestPartException.class
    })
    public ResponseEntity<ApiError> handleValidation(
            Exception exception,
            HttpServletRequest request
    ) {
        return error(
                HttpStatus.BAD_REQUEST,
                "VALIDATION_ERROR",
                "Request validation failed.",
                request
        );
    }

    @ExceptionHandler(ConversationNotFoundException.class)
    public ResponseEntity<ApiError> handleConversationNotFound(
            ConversationNotFoundException exception,
            HttpServletRequest request
    ) {
        return error(
                HttpStatus.NOT_FOUND,
                "CONVERSATION_NOT_FOUND",
                "The requested conversation does not exist.",
                request
        );
    }

    @ExceptionHandler(MemoryNotFoundException.class)
    public ResponseEntity<ApiError> handleMemoryNotFound(
            MemoryNotFoundException exception,
            HttpServletRequest request
    ) {
        return error(
                HttpStatus.NOT_FOUND,
                "MEMORY_NOT_FOUND",
                "The requested memory does not exist.",
                request
        );
    }

    @ExceptionHandler(MemoryValidationException.class)
    public ResponseEntity<ApiError> handleInvalidArgument(
            MemoryValidationException exception,
            HttpServletRequest request
    ) {
        return error(
                HttpStatus.BAD_REQUEST,
                "VALIDATION_ERROR",
                "Request validation failed.",
                request
        );
    }

    @ExceptionHandler(ForumPostNotFoundException.class)
    public ResponseEntity<ApiError> handleForumPostNotFound(
            ForumPostNotFoundException exception,
            HttpServletRequest request
    ) {
        return error(
                HttpStatus.NOT_FOUND,
                "FORUM_POST_NOT_FOUND",
                "The requested forum post does not exist.",
                request
        );
    }

    @ExceptionHandler(ForumPostImageNotFoundException.class)
    public ResponseEntity<ApiError> handleForumPostImageNotFound(
            ForumPostImageNotFoundException exception,
            HttpServletRequest request
    ) {
        return error(
                HttpStatus.NOT_FOUND,
                "FORUM_IMAGE_NOT_FOUND",
                "The requested forum post does not have an image.",
                request
        );
    }

    @ExceptionHandler(InsufficientConversationException.class)
    public ResponseEntity<ApiError> handleInsufficientConversation(
            InsufficientConversationException exception,
            HttpServletRequest request
    ) {
        return error(
                HttpStatus.BAD_REQUEST,
                "INSUFFICIENT_CONVERSATION",
                "The conversation does not contain enough content for a forum draft.",
                request
        );
    }

    @ExceptionHandler(ConversationModelConflictException.class)
    public ResponseEntity<ApiError> handleConversationModelConflict(
            ConversationModelConflictException exception,
            HttpServletRequest request
    ) {
        return error(
                HttpStatus.CONFLICT,
                "CONVERSATION_MODEL_CONFLICT",
                "Use the model-switch endpoint to change an existing conversation model.",
                request
        );
    }

    @ExceptionHandler({
            ModelUnavailableException.class,
            ModelCapabilityException.class
    })
    public ResponseEntity<ApiError> handleModelRequest(
            RuntimeException exception,
            HttpServletRequest request
    ) {
        String message = exception instanceof ModelCapabilityException
                ? "The selected model does not support image input."
                : "The selected model is not currently available.";
        return error(
                HttpStatus.BAD_REQUEST,
                "MODEL_NOT_AVAILABLE",
                message,
                request
        );
    }

    @ExceptionHandler(ImageNotFoundException.class)
    public ResponseEntity<ApiError> handleImageNotFound(
            ImageNotFoundException exception,
            HttpServletRequest request
    ) {
        return error(
                HttpStatus.NOT_FOUND,
                "IMAGE_NOT_FOUND",
                "The requested image does not exist.",
                request
        );
    }

    @ExceptionHandler(GeneratedImageNotFoundException.class)
    public ResponseEntity<ApiError> handleGeneratedImageNotFound(
            GeneratedImageNotFoundException exception,
            HttpServletRequest request
    ) {
        return error(
                HttpStatus.NOT_FOUND,
                "GENERATED_IMAGE_NOT_FOUND",
                "The requested generated image does not exist.",
                request
        );
    }

    @ExceptionHandler(InvalidImageException.class)
    public ResponseEntity<ApiError> handleInvalidImage(
            InvalidImageException exception,
            HttpServletRequest request
    ) {
        return error(
                HttpStatus.BAD_REQUEST,
                "INVALID_IMAGE",
                "The uploaded file is not a supported image.",
                request
        );
    }

    @ExceptionHandler({
            ImageTooLargeException.class,
            MaxUploadSizeExceededException.class
    })
    public ResponseEntity<ApiError> handleImageTooLarge(
            Exception exception,
            HttpServletRequest request
    ) {
        return error(
                HttpStatus.PAYLOAD_TOO_LARGE,
                "IMAGE_TOO_LARGE",
                "The uploaded image exceeds the maximum allowed size.",
                request
        );
    }

    @ExceptionHandler(ImageStorageException.class)
    public ResponseEntity<ApiError> handleImageStorageFailure(
            ImageStorageException exception,
            HttpServletRequest request
    ) {
        LOGGER.error(
                "Image storage failure for {} ({})",
                request.getRequestURI(),
                exception.getClass().getSimpleName()
        );
        return error(
                HttpStatus.SERVICE_UNAVAILABLE,
                "IMAGE_STORAGE_UNAVAILABLE",
                "Image storage is temporarily unavailable.",
                request
        );
    }

    @ExceptionHandler(UsernameAlreadyExistsException.class)
    public ResponseEntity<ApiError> handleUsernameAlreadyExists(
            UsernameAlreadyExistsException exception,
            HttpServletRequest request
    ) {
        return error(
                HttpStatus.CONFLICT,
                "USERNAME_ALREADY_EXISTS",
                "The username is already registered.",
                request
        );
    }

    @ExceptionHandler(InvalidLoginException.class)
    public ResponseEntity<ApiError> handleInvalidLogin(
            InvalidLoginException exception,
            HttpServletRequest request
    ) {
        return error(
                HttpStatus.UNAUTHORIZED,
                "INVALID_CREDENTIALS",
                "Invalid username or password.",
                request
        );
    }

    @ExceptionHandler(PasswordTooLongException.class)
    public ResponseEntity<ApiError> handlePasswordTooLong(
            PasswordTooLongException exception,
            HttpServletRequest request
    ) {
        return error(
                HttpStatus.BAD_REQUEST,
                "VALIDATION_ERROR",
                "Request validation failed.",
                request
        );
    }

    @ExceptionHandler(DataAccessException.class)
    public ResponseEntity<ApiError> handleDatabaseFailure(
            DataAccessException exception,
            HttpServletRequest request
    ) {
        DatabaseFailureDiagnostics details =
                DatabaseFailureDiagnostics.inspect(exception);
        LOGGER.error(
                "business_storage_failure operation={} {} exception={} "
                        + "rootCause={} sqlState={} vendorCode={}",
                request.getMethod(),
                request.getRequestURI(),
                details.exceptionClass(),
                details.rootCauseClass(),
                details.sqlState(),
                details.vendorCode()
        );
        return error(
                HttpStatus.SERVICE_UNAVAILABLE,
                "DATABASE_ERROR",
                "Business storage is temporarily unavailable.",
                request
        );
    }

    @ExceptionHandler(BusinessStorageOperationException.class)
    public ResponseEntity<ApiError> handleBusinessStorageOperationFailure(
            BusinessStorageOperationException exception,
            HttpServletRequest request
    ) {
        DatabaseFailureDiagnostics details =
                DatabaseFailureDiagnostics.inspect(exception.getCause());
        LOGGER.error(
                "business_storage_failure operation={} {} {} exception={} "
                        + "rootCause={} sqlState={} vendorCode={}",
                exception.getOperation(),
                request.getMethod(),
                request.getRequestURI(),
                details.exceptionClass(),
                details.rootCauseClass(),
                details.sqlState(),
                details.vendorCode()
        );
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body(
                new ApiError(
                        "BUSINESS_STORAGE_ERROR",
                        "Business storage is temporarily unavailable.",
                        HttpStatus.SERVICE_UNAVAILABLE.value(),
                        request.getRequestURI(),
                        exception.getOperation()
                )
        );
    }

    @ExceptionHandler(AiServiceRejectedRequestException.class)
    public ResponseEntity<ApiError> handleAiRejectedRequest(
            AiServiceRejectedRequestException exception,
            HttpServletRequest request
    ) {
        return error(
                HttpStatus.BAD_REQUEST,
                "AI_REQUEST_REJECTED",
                "The AI service rejected the request.",
                request
        );
    }

    @ExceptionHandler(AiServiceUnavailableException.class)
    public ResponseEntity<ApiError> handleAiUnavailable(
            AiServiceUnavailableException exception,
            HttpServletRequest request
    ) {
        return error(
                HttpStatus.SERVICE_UNAVAILABLE,
                "AI_SERVICE_UNAVAILABLE",
                "The AI service is temporarily unavailable.",
                request
        );
    }

    @ExceptionHandler(AiServiceTimeoutException.class)
    public ResponseEntity<ApiError> handleAiTimeout(
            AiServiceTimeoutException exception,
            HttpServletRequest request
    ) {
        return error(
                HttpStatus.GATEWAY_TIMEOUT,
                "AI_SERVICE_TIMEOUT",
                "The AI service did not respond in time.",
                request
        );
    }

    @ExceptionHandler(AiServiceServerException.class)
    public ResponseEntity<ApiError> handleAiServerError(
            AiServiceServerException exception,
            HttpServletRequest request
    ) {
        return error(
                HttpStatus.BAD_GATEWAY,
                "AI_SERVICE_ERROR",
                "The AI service could not complete the request.",
                request
        );
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiError> handleUnexpected(
            Exception exception,
            HttpServletRequest request
    ) {
        LOGGER.error(
                "Unexpected backend failure for {}",
                request.getRequestURI(),
                exception
        );
        return error(
                HttpStatus.INTERNAL_SERVER_ERROR,
                "INTERNAL_ERROR",
                "An unexpected backend error occurred.",
                request
        );
    }

    private static ResponseEntity<ApiError> error(
            HttpStatus status,
            String code,
            String message,
            HttpServletRequest request
    ) {
        return ResponseEntity.status(status).body(new ApiError(
                code,
                message,
                status.value(),
                request.getRequestURI()
        ));
    }
}
