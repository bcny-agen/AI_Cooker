package com.aicooker.backend.exception;

import static org.assertj.core.api.Assertions.assertThat;

import java.sql.SQLException;

import org.junit.jupiter.api.Test;
import org.springframework.dao.DataAccessResourceFailureException;

class DatabaseFailureDiagnosticsTest {

    @Test
    void extractsSafeRootCauseAndSqlCodesWithoutRequestData() {
        var sqlFailure = new SQLException(
                "synthetic connection failure",
                "08006",
                2013
        );
        var failure = new DataAccessResourceFailureException(
                "synthetic business persistence failure",
                sqlFailure
        );

        DatabaseFailureDiagnostics details =
                DatabaseFailureDiagnostics.inspect(failure);

        assertThat(details.exceptionClass())
                .isEqualTo("DataAccessResourceFailureException");
        assertThat(details.rootCauseClass()).isEqualTo("SQLException");
        assertThat(details.sqlState()).isEqualTo("08006");
        assertThat(details.vendorCode()).isEqualTo(2013);
    }
}
