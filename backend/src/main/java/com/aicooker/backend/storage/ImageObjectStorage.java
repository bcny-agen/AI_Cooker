package com.aicooker.backend.storage;

import java.io.InputStream;
import java.net.URI;

public interface ImageObjectStorage {

    void upload(
            String objectKey,
            InputStream inputStream,
            long size,
            String contentType
    );

    URI createReadUrl(String objectKey);

    boolean exists(String objectKey);

    void delete(String objectKey);
}
