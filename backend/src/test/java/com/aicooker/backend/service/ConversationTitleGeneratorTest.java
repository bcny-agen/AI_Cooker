package com.aicooker.backend.service;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class ConversationTitleGeneratorTest {

    private final ConversationTitleGenerator titleGenerator =
            new ConversationTitleGenerator();

    @Test
    void normalizesWhitespaceForShortTitles() {
        assertThat(titleGenerator.generate("  Tomato   eggs\nrecipe  "))
                .isEqualTo("Tomato eggs recipe");
    }

    @Test
    void truncatesByUnicodeCodePointWithoutSplittingCharacters() {
        String title = titleGenerator.generate("菜".repeat(70));

        assertThat(title.codePointCount(0, title.length()))
                .isEqualTo(ConversationTitleGenerator.MAX_TITLE_CODE_POINTS);
        assertThat(title).endsWith("…");
    }
}
