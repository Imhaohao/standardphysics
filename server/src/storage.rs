use std::time::Duration;

use anyhow::{anyhow, Context, Result};
use aws_sdk_s3::config::{
    BehaviorVersion, Credentials, Region, RequestChecksumCalculation, ResponseChecksumValidation,
};
use aws_sdk_s3::presigning::PresigningConfig;
use aws_sdk_s3::types::{CompletedMultipartUpload, CompletedPart};
use aws_sdk_s3::Client;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use utoipa::ToSchema;

use crate::config::StorageConfig;

#[derive(Clone)]
pub struct Storage {
    client: Client,
    bucket: String,
    presign_ttl: Duration,
}

#[derive(Clone, Debug, Serialize, Deserialize, ToSchema)]
pub struct PresignedPart {
    pub part_number: i32,
    pub url: String,
    pub headers: Vec<(String, String)>,
}

#[derive(Clone, Debug, Serialize, Deserialize, ToSchema)]
pub struct UploadedPart {
    pub part_number: i32,
    pub etag: String,
    pub size_bytes: i64,
}

fn build_client(cfg: &StorageConfig) -> Client {
    let credentials = Credentials::new(
        cfg.access_key_id.clone(),
        cfg.secret_access_key.clone(),
        None,
        None,
        "sp-server-env",
    );
    let mut builder = aws_sdk_s3::Config::builder()
        .behavior_version(BehaviorVersion::latest())
        .region(Region::new(cfg.region.clone()))
        .credentials_provider(credentials)
        .force_path_style(cfg.force_path_style)
        .request_checksum_calculation(RequestChecksumCalculation::WhenRequired)
        .response_checksum_validation(ResponseChecksumValidation::WhenRequired);
    if let Some(endpoint) = &cfg.endpoint {
        builder = builder.endpoint_url(endpoint.clone());
    }
    Client::from_conf(builder.build())
}

impl Storage {
    pub fn new(cfg: &StorageConfig) -> Self {
        Self {
            client: build_client(cfg),
            bucket: cfg.bucket.clone(),
            presign_ttl: cfg.presign_ttl,
        }
    }

    pub async fn check_bucket(&self) -> Result<()> {
        self.client
            .head_bucket()
            .bucket(&self.bucket)
            .send()
            .await
            .map_err(|e| anyhow!("head_bucket failed: {e:?}"))?;
        Ok(())
    }

    pub async fn create_multipart(&self, key: &str, content_type: &str) -> Result<String> {
        let out = self
            .client
            .create_multipart_upload()
            .bucket(&self.bucket)
            .key(key)
            .content_type(content_type)
            .send()
            .await
            .map_err(|e| anyhow!("create_multipart_upload failed: {e:?}"))?;
        out.upload_id()
            .map(str::to_string)
            .context("storage returned no upload id")
    }

    pub async fn presign_part(
        &self,
        key: &str,
        upload_id: &str,
        part_number: i32,
    ) -> Result<PresignedPart> {
        let presign = PresigningConfig::expires_in(self.presign_ttl)?;
        let request = self
            .client
            .upload_part()
            .bucket(&self.bucket)
            .key(key)
            .upload_id(upload_id)
            .part_number(part_number)
            .presigned(presign)
            .await
            .map_err(|e| anyhow!("presign failed: {e:?}"))?;
        Ok(PresignedPart {
            part_number,
            url: request.uri().to_string(),
            headers: request
                .headers()
                .map(|(k, v)| (k.to_string(), v.to_string()))
                .collect(),
        })
    }

    pub async fn list_parts(&self, key: &str, upload_id: &str) -> Result<Vec<UploadedPart>> {
        let mut parts = Vec::new();
        let mut marker: Option<String> = None;
        loop {
            let out = self
                .client
                .list_parts()
                .bucket(&self.bucket)
                .key(key)
                .upload_id(upload_id)
                .set_part_number_marker(marker.clone())
                .send()
                .await
                .map_err(|e| anyhow!("list_parts failed: {e:?}"))?;
            parts.extend(out.parts().iter().map(uploaded_part));
            if !out.is_truncated().unwrap_or(false) {
                return Ok(parts);
            }
            marker = out.next_part_number_marker().map(str::to_string);
        }
    }

    pub async fn complete_multipart(
        &self,
        key: &str,
        upload_id: &str,
        parts: &[(i32, String)],
    ) -> Result<()> {
        let completed = parts
            .iter()
            .map(|(number, etag)| {
                CompletedPart::builder()
                    .part_number(*number)
                    .e_tag(etag)
                    .build()
            })
            .collect::<Vec<_>>();
        self.client
            .complete_multipart_upload()
            .bucket(&self.bucket)
            .key(key)
            .upload_id(upload_id)
            .multipart_upload(
                CompletedMultipartUpload::builder()
                    .set_parts(Some(completed))
                    .build(),
            )
            .send()
            .await
            .map_err(|e| anyhow!("complete_multipart_upload failed: {e:?}"))?;
        Ok(())
    }

    pub async fn abort_multipart(&self, key: &str, upload_id: &str) -> Result<()> {
        self.client
            .abort_multipart_upload()
            .bucket(&self.bucket)
            .key(key)
            .upload_id(upload_id)
            .send()
            .await
            .map_err(|e| anyhow!("abort_multipart_upload failed: {e:?}"))?;
        Ok(())
    }

    pub async fn object_size(&self, key: &str) -> Result<u64> {
        let out = self
            .client
            .head_object()
            .bucket(&self.bucket)
            .key(key)
            .send()
            .await
            .map_err(|e| anyhow!("head_object failed: {e:?}"))?;
        Ok(out.content_length().unwrap_or(0).max(0) as u64)
    }

    pub async fn delete_object(&self, key: &str) -> Result<()> {
        self.client
            .delete_object()
            .bucket(&self.bucket)
            .key(key)
            .send()
            .await
            .map_err(|e| anyhow!("delete_object failed: {e:?}"))?;
        Ok(())
    }

    pub async fn get_bytes(&self, key: &str) -> Result<Vec<u8>> {
        let out = self
            .client
            .get_object()
            .bucket(&self.bucket)
            .key(key)
            .send()
            .await
            .map_err(|e| anyhow!("get_object failed: {e:?}"))?;
        Ok(out.body.collect().await?.into_bytes().to_vec())
    }

    pub async fn sha256_hex(&self, key: &str) -> Result<String> {
        let mut out = self
            .client
            .get_object()
            .bucket(&self.bucket)
            .key(key)
            .send()
            .await
            .map_err(|e| anyhow!("get_object failed: {e:?}"))?;
        let mut hasher = Sha256::new();
        while let Some(chunk) = out.body.try_next().await? {
            hasher.update(&chunk);
        }
        Ok(hex::encode(hasher.finalize()))
    }
}

fn uploaded_part(part: &aws_sdk_s3::types::Part) -> UploadedPart {
    UploadedPart {
        part_number: part.part_number().unwrap_or(0),
        etag: part.e_tag().unwrap_or_default().to_string(),
        size_bytes: part.size().unwrap_or(0),
    }
}
