package com.aicooker.backend.config;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.util.unit.DataSize;

@ConfigurationProperties(prefix = "aliyun.oss")
public record OssProperties(
        URI endpoint,
        String region,
        String bucketName,
        String accessKeyId,
        String accessKeySecret,
        Duration signedUrlTtl,
        DataSize maxFileSize
) {

    public OssProperties {
        if (endpoint == null
                || endpoint.getHost() == null
                || !"https".equalsIgnoreCase(endpoint.getScheme())) {
            throw new IllegalArgumentException(
                    "aliyun.oss.endpoint must be an absolute HTTPS URL"
            );
        }
        requireText(region, "aliyun.oss.region");
        requireText(bucketName, "aliyun.oss.bucket-name");
        requireText(accessKeyId, "aliyun.oss.access-key-id");
        requireText(accessKeySecret, "aliyun.oss.access-key-secret");
        if (signedUrlTtl == null
                || signedUrlTtl.isZero()
                || signedUrlTtl.isNegative()
                || signedUrlTtl.compareTo(Duration.ofDays(7)) > 0) {
            throw new IllegalArgumentException(
                    "aliyun.oss.signed-url-ttl must be positive and at most 7 days"
            );
        }
        if (maxFileSize == null || maxFileSize.toBytes() <= 0) {
            throw new IllegalArgumentException(
                    "aliyun.oss.max-file-size must be positive"
            );
        }
    }

    private static void requireText(String value, String propertyName) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(propertyName + " must not be blank");
        }
    }
}
