package com.aicooker.backend.exception;

import java.sql.SQLException;

public record DatabaseFailureDiagnostics(
        String exceptionClass,
        String rootCauseClass,
        String sqlState,
        Integer vendorCode
) {

    public static DatabaseFailureDiagnostics inspect(Throwable exception) {
        Throwable current = exception;
        Throwable rootCause = exception;
        SQLException sqlException = null;
        while (current != null) {
            rootCause = current;
            if (current instanceof SQLException candidate) {
                sqlException = candidate;
            }
            current = current.getCause();
        }
        return new DatabaseFailureDiagnostics(
                exception.getClass().getSimpleName(),
                rootCause.getClass().getSimpleName(),
                sqlException == null ? "n/a" : sqlException.getSQLState(),
                sqlException == null ? null : sqlException.getErrorCode()
        );
    }
}
