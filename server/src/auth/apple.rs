use std::time::{Duration, Instant};

use anyhow::{anyhow, Context, Result};
use jsonwebtoken::jwk::JwkSet;
use jsonwebtoken::{decode, decode_header, Algorithm, DecodingKey, Validation};
use serde::Deserialize;
use sha2::{Digest, Sha256};
use tokio::sync::RwLock;

use crate::config::AppleConfig;

const APPLE_ISSUER: &str = "https://appleid.apple.com";
const MIN_REFETCH_INTERVAL: Duration = Duration::from_secs(30);

#[derive(Debug, Clone)]
pub struct AppleIdentity {
    pub subject: String,
    pub email: Option<String>,
}

#[derive(Deserialize)]
struct AppleClaims {
    sub: String,
    email: Option<String>,
    nonce: Option<String>,
}

struct CachedKeys {
    fetched_at: Instant,
    keys: JwkSet,
}

pub struct AppleVerifier {
    cfg: AppleConfig,
    http: reqwest::Client,
    cache: RwLock<Option<CachedKeys>>,
}

impl AppleVerifier {
    pub fn new(cfg: AppleConfig) -> Self {
        Self {
            cfg,
            http: reqwest::Client::new(),
            cache: RwLock::new(None),
        }
    }

    pub fn is_configured(&self) -> bool {
        !self.cfg.bundle_id.is_empty()
    }

    pub async fn verify(&self, identity_token: &str, raw_nonce: &str) -> Result<AppleIdentity> {
        if !self.is_configured() {
            return Err(anyhow!("apple sign-in is not configured"));
        }
        let header = decode_header(identity_token).context("malformed identity token")?;
        let kid = header.kid.context("identity token has no key id")?;
        let key = self.decoding_key(&kid).await?;
        let claims = decode::<AppleClaims>(identity_token, &key, &self.validation())
            .context("identity token rejected")?
            .claims;
        check_nonce(claims.nonce.as_deref(), raw_nonce)?;
        Ok(AppleIdentity {
            subject: claims.sub,
            email: claims.email,
        })
    }

    fn validation(&self) -> Validation {
        let mut validation = Validation::new(Algorithm::RS256);
        validation.set_audience(&[&self.cfg.bundle_id]);
        validation.set_issuer(&[APPLE_ISSUER]);
        validation.set_required_spec_claims(&["exp", "iss", "aud", "sub"]);
        validation
    }

    async fn decoding_key(&self, kid: &str) -> Result<DecodingKey> {
        if let Some(key) = self.cached_key(kid).await? {
            return Ok(key);
        }
        self.refresh_keys().await?;
        self.cached_key(kid)
            .await?
            .ok_or_else(|| anyhow!("no apple signing key matches kid {kid}"))
    }

    async fn cached_key(&self, kid: &str) -> Result<Option<DecodingKey>> {
        let guard = self.cache.read().await;
        let Some(cached) = guard.as_ref() else {
            return Ok(None);
        };
        if cached.fetched_at.elapsed() > self.cfg.jwks_ttl {
            return Ok(None);
        }
        let Some(jwk) = cached.keys.find(kid) else {
            return Ok(None);
        };
        Ok(Some(DecodingKey::from_jwk(jwk)?))
    }

    async fn refresh_keys(&self) -> Result<()> {
        let mut guard = self.cache.write().await;
        if guard.as_ref().is_some_and(recently_fetched) {
            return Ok(());
        }
        let keys: JwkSet = self
            .http
            .get(&self.cfg.jwks_url)
            .timeout(Duration::from_secs(10))
            .send()
            .await?
            .error_for_status()?
            .json()
            .await
            .context("apple JWKS was not valid JSON")?;
        *guard = Some(CachedKeys {
            fetched_at: Instant::now(),
            keys,
        });
        Ok(())
    }
}

fn recently_fetched(cached: &CachedKeys) -> bool {
    cached.fetched_at.elapsed() < MIN_REFETCH_INTERVAL
}

fn check_nonce(claim: Option<&str>, raw_nonce: &str) -> Result<()> {
    let expected = hex::encode(Sha256::digest(raw_nonce.as_bytes()));
    match claim {
        Some(value) if !raw_nonce.is_empty() && value.eq_ignore_ascii_case(&expected) => Ok(()),
        _ => Err(anyhow!("nonce missing or mismatched")),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn nonce_must_be_the_sha256_hex_of_the_raw_nonce() {
        let hashed = hex::encode(Sha256::digest(b"abc"));
        assert!(check_nonce(Some(&hashed), "abc").is_ok());
        assert!(check_nonce(Some(&hashed.to_uppercase()), "abc").is_ok());
        assert!(
            check_nonce(Some("abc"), "abc").is_err(),
            "raw nonce in the claim is not accepted"
        );
        assert!(check_nonce(Some("zzz"), "abc").is_err());
        assert!(check_nonce(None, "abc").is_err());
        assert!(check_nonce(Some(&hashed), "").is_err());
    }
}
