package com.aicooker.backend.storage;

import java.io.InputStream;
import java.net.URI;
import java.net.URISyntaxException;
import java.time.Clock;
import java.util.Date;

import com.aicooker.backend.config.OssProperties;
import com.aicooker.backend.exception.ImageStorageException;
import com.aliyun.oss.ClientException;
import com.aliyun.oss.HttpMethod;
import com.aliyun.oss.OSS;
import com.aliyun.oss.OSSException;
import com.aliyun.oss.model.GeneratePresignedUrlRequest;
import com.aliyun.oss.model.CannedAccessControlList;
import com.aliyun.oss.model.ObjectMetadata;
import com.aliyun.oss.model.PutObjectRequest;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class AlibabaOssImageObjectStorage implements ImageObjectStorage {

    private static final Logger LOGGER = LoggerFactory.getLogger(
            AlibabaOssImageObjectStorage.class
    );

    private final OSS ossClient;
    private final OssProperties properties;
    private final Clock clock;

    public AlibabaOssImageObjectStorage(
            OSS ossClient,
            OssProperties properties,
            Clock clock
    ) {
        this.ossClient = ossClient;
        this.properties = properties;
        this.clock = clock;
    }

    @Override
    public void upload(
            String objectKey,
            InputStream inputStream,
            long size,
            String contentType
    ) {
        try {
            var metadata = new ObjectMetadata();
            metadata.setContentLength(size);
            metadata.setContentType(contentType);
            metadata.setObjectAcl(CannedAccessControlList.Private);
            ossClient.putObject(new PutObjectRequest(
                    properties.bucketName(),
                    objectKey,
                    inputStream,
                    metadata
            ));
        } catch (OSSException exception) {
            LOGGER.error(
                    "OSS upload rejected (code={})",
                    exception.getErrorCode()
            );
            throw new ImageStorageException("OSS upload failed.", exception);
        } catch (ClientException exception) {
            LOGGER.error(
                    "OSS upload client failure (code={})",
                    exception.getErrorCode()
            );
            throw new ImageStorageException("OSS upload failed.", exception);
        }
    }

    @Override
    public URI createReadUrl(String objectKey) {
        try {
            var request = new GeneratePresignedUrlRequest(
                    properties.bucketName(),
                    objectKey,
                    HttpMethod.GET
            );
            request.setExpiration(Date.from(
                    clock.instant().plus(properties.signedUrlTtl())
            ));
            URI uri = ossClient.generatePresignedUrl(request).toURI();
            if (!"https".equalsIgnoreCase(uri.getScheme())) {
                throw new ImageStorageException(
                        "OSS generated a non-HTTPS image URL."
                );
            }
            return uri;
        } catch (OSSException | ClientException | URISyntaxException exception) {
            throw new ImageStorageException(
                    "OSS signed URL generation failed.",
                    exception
            );
        }
    }

    @Override
    public boolean exists(String objectKey) {
        try {
            return ossClient.doesObjectExist(properties.bucketName(), objectKey);
        } catch (OSSException | ClientException exception) {
            throw new ImageStorageException(
                    "OSS object existence check failed.",
                    exception
            );
        }
    }

    @Override
    public void delete(String objectKey) {
        try {
            ossClient.deleteObject(properties.bucketName(), objectKey);
        } catch (OSSException | ClientException exception) {
            throw new ImageStorageException("OSS object deletion failed.", exception);
        }
    }
}
