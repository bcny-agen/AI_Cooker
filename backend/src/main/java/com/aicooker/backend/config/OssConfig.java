package com.aicooker.backend.config;

import com.aliyun.oss.ClientBuilderConfiguration;
import com.aliyun.oss.OSS;
import com.aliyun.oss.OSSClientBuilder;
import com.aliyun.oss.common.auth.DefaultCredentialProvider;
import com.aliyun.oss.common.comm.SignVersion;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(OssProperties.class)
public class OssConfig {

    @Bean(destroyMethod = "shutdown")
    OSS ossClient(OssProperties properties) {
        var clientConfiguration = new ClientBuilderConfiguration();
        clientConfiguration.setSignatureVersion(SignVersion.V4);
        var credentials = new DefaultCredentialProvider(
                properties.accessKeyId(),
                properties.accessKeySecret()
        );

        return OSSClientBuilder.create()
                .endpoint(properties.endpoint().toString())
                .credentialsProvider(credentials)
                .clientConfiguration(clientConfiguration)
                .region(properties.region())
                .build();
    }
}
