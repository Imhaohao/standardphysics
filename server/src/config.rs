use std::time::Duration;

use anyhow::{anyhow, Result};

pub const DEFAULT_APPLE_JWKS_URL: &str = "https://appleid.apple.com/auth/keys";
pub const DEFAULT_LABEL_API_BASE: &str = "https://openrouter.ai/api/v1";
pub const DEFAULT_LABEL_MODEL: &str = "google/gemini-3.8-flash";

#[derive(Clone, Debug)]
pub struct StorageConfig {
    pub endpoint: Option<String>,
    pub public_endpoint: Option<String>,
    pub allow_insecure_public_endpoint: bool,
    pub region: String,
    pub bucket: String,
    pub access_key_id: String,
    pub secret_access_key: String,
    pub force_path_style: bool,
    pub presign_ttl: Duration,
    pub verify_max_bytes: u64,
}

#[derive(Clone, Debug)]
pub struct AppleConfig {
    pub bundle_id: String,
    pub jwks_url: String,
    pub jwks_ttl: Duration,
}

#[derive(Clone, Debug)]
pub struct LabelConfig {
    pub api_base: String,
    pub api_key: Option<String>,
    pub model: String,
    pub concurrency: usize,
    pub deadline: Duration,
    pub request_timeout: Duration,
}

#[derive(Clone, Debug)]
pub struct Config {
    pub bind_addr: String,
    pub database_url: String,
    pub db_max_connections: u32,
    pub run_migrations: bool,
    pub session_ttl: Duration,
    pub cors_origins: Vec<String>,
    pub job_poll: Duration,
    pub run_job_worker: bool,
    pub storage: StorageConfig,
    pub apple: AppleConfig,
    pub label: LabelConfig,
}

pub struct Env<F: Fn(&str) -> Option<String>> {
    lookup: F,
}

impl<F: Fn(&str) -> Option<String>> Env<F> {
    pub fn new(lookup: F) -> Self {
        Self { lookup }
    }

    fn optional(&self, key: &str) -> Option<String> {
        (self.lookup)(key).filter(|v| !v.trim().is_empty())
    }

    fn required(&self, key: &str) -> Result<String> {
        self.optional(key)
            .ok_or_else(|| anyhow!("missing required env var {key}"))
    }

    fn or_default(&self, key: &str, default: &str) -> String {
        self.optional(key).unwrap_or_else(|| default.to_string())
    }

    fn parsed<T: std::str::FromStr>(&self, key: &str, default: T) -> Result<T> {
        match self.optional(key) {
            None => Ok(default),
            Some(raw) => raw
                .parse()
                .map_err(|_| anyhow!("env var {key} has an invalid value: {raw}")),
        }
    }

    fn flag(&self, key: &str, default: bool) -> Result<bool> {
        self.parsed(key, default)
    }

    fn list(&self, key: &str) -> Vec<String> {
        self.optional(key)
            .map(|raw| {
                raw.split(',')
                    .map(|part| part.trim().to_string())
                    .filter(|part| !part.is_empty())
                    .collect()
            })
            .unwrap_or_default()
    }
}

impl Config {
    pub fn from_env() -> Result<Self> {
        Self::from_lookup(|key| std::env::var(key).ok())
    }

    pub fn from_lookup(lookup: impl Fn(&str) -> Option<String>) -> Result<Self> {
        let env = Env::new(lookup);
        Ok(Self {
            bind_addr: bind_addr(&env),
            database_url: env.required("DATABASE_URL")?,
            db_max_connections: env.parsed("DB_MAX_CONNECTIONS", 10)?,
            run_migrations: env.flag("RUN_MIGRATIONS", true)?,
            session_ttl: Duration::from_secs(env.parsed("SESSION_TTL_DAYS", 90u64)? * 86_400),
            cors_origins: env.list("CORS_ALLOWED_ORIGINS"),
            job_poll: Duration::from_millis(env.parsed("JOB_POLL_MS", 1000)?),
            run_job_worker: env.flag("RUN_JOB_WORKER", true)?,
            storage: storage_config(&env)?,
            apple: apple_config(&env)?,
            label: label_config(&env)?,
        })
    }
}

fn bind_addr<F: Fn(&str) -> Option<String>>(env: &Env<F>) -> String {
    if let Some(addr) = env.optional("BIND_ADDR") {
        return addr;
    }
    format!("0.0.0.0:{}", env.or_default("PORT", "8080"))
}

fn storage_config<F: Fn(&str) -> Option<String>>(env: &Env<F>) -> Result<StorageConfig> {
    let endpoint = env.optional("S3_ENDPOINT");
    let force_path_style = env.flag("S3_FORCE_PATH_STYLE", endpoint.is_some())?;
    let public_endpoint = env
        .optional("S3_PUBLIC_ENDPOINT")
        .or_else(|| endpoint.clone());
    let allow_insecure = env.flag("S3_ALLOW_INSECURE_PUBLIC_ENDPOINT", false)?;
    require_https(public_endpoint.as_deref(), allow_insecure)?;
    Ok(StorageConfig {
        endpoint,
        public_endpoint,
        allow_insecure_public_endpoint: allow_insecure,
        region: env.or_default("S3_REGION", "auto"),
        bucket: env.required("S3_BUCKET")?,
        access_key_id: env.required("S3_ACCESS_KEY_ID")?,
        secret_access_key: env.required("S3_SECRET_ACCESS_KEY")?,
        force_path_style,
        presign_ttl: Duration::from_secs(env.parsed("S3_PRESIGN_TTL_SECS", 3600)?),
        verify_max_bytes: env.parsed("UPLOAD_VERIFY_MAX_BYTES", 64 * 1024 * 1024)?,
    })
}

fn apple_config<F: Fn(&str) -> Option<String>>(env: &Env<F>) -> Result<AppleConfig> {
    Ok(AppleConfig {
        bundle_id: env.or_default("APPLE_BUNDLE_ID", ""),
        jwks_url: env.or_default("APPLE_JWKS_URL", DEFAULT_APPLE_JWKS_URL),
        jwks_ttl: Duration::from_secs(env.parsed("APPLE_JWKS_TTL_SECS", 3600)?),
    })
}

fn label_config<F: Fn(&str) -> Option<String>>(env: &Env<F>) -> Result<LabelConfig> {
    Ok(LabelConfig {
        api_base: env.or_default("LABEL_API_BASE", DEFAULT_LABEL_API_BASE),
        api_key: env.optional("LABEL_API_KEY"),
        model: env.or_default("LABEL_MODEL", DEFAULT_LABEL_MODEL),
        concurrency: env.parsed("LABEL_CONCURRENCY", 8)?,
        deadline: Duration::from_millis(env.parsed("LABEL_DEADLINE_MS", 20_000)?),
        request_timeout: Duration::from_millis(env.parsed("LABEL_REQUEST_TIMEOUT_MS", 15_000)?),
    })
}

fn require_https(endpoint: Option<&str>, allow_insecure: bool) -> Result<()> {
    match endpoint {
        Some(url) if !url.starts_with("https://") && !allow_insecure => Err(anyhow!(
            "S3_PUBLIC_ENDPOINT (or S3_ENDPOINT) must be https; set S3_ALLOW_INSECURE_PUBLIC_ENDPOINT=true for local development"
        )),
        _ => Ok(()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn lookup(extra: &[(&'static str, &'static str)]) -> Result<Config> {
        let mut vars: std::collections::HashMap<&str, &str> = std::collections::HashMap::from([
            ("DATABASE_URL", "postgres://x"),
            ("S3_BUCKET", "b"),
            ("S3_ACCESS_KEY_ID", "k"),
            ("S3_SECRET_ACCESS_KEY", "s"),
        ]);
        vars.extend(extra.iter().copied());
        Config::from_lookup(|k| vars.get(k).map(|v| v.to_string()))
    }

    #[test]
    fn plain_http_public_endpoint_is_rejected_unless_flagged() {
        assert!(lookup(&[("S3_ENDPOINT", "http://minio:9000")]).is_err());
        assert!(lookup(&[("S3_PUBLIC_ENDPOINT", "http://x.example")]).is_err());
        assert!(lookup(&[
            ("S3_ENDPOINT", "http://minio:9000"),
            ("S3_ALLOW_INSECURE_PUBLIC_ENDPOINT", "true")
        ])
        .is_ok());
        assert!(lookup(&[("S3_ENDPOINT", "https://acct.r2.cloudflarestorage.com")]).is_ok());
        assert!(lookup(&[]).is_ok());
    }

    #[test]
    fn public_endpoint_defaults_to_the_storage_endpoint() {
        let cfg = lookup(&[
            ("S3_ENDPOINT", "https://internal.example"),
            ("S3_PUBLIC_ENDPOINT", "https://public.example"),
        ])
        .unwrap();
        assert_eq!(
            cfg.storage.public_endpoint.as_deref(),
            Some("https://public.example")
        );
        let cfg = lookup(&[("S3_ENDPOINT", "https://internal.example")]).unwrap();
        assert_eq!(
            cfg.storage.public_endpoint.as_deref(),
            Some("https://internal.example")
        );
    }
}
