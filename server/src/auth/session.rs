use std::time::Duration;

use anyhow::Result;
use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use base64::Engine;
use chrono::{DateTime, Utc};
use rand::RngCore;
use sha2::{Digest, Sha256};
use sqlx::PgPool;
use uuid::Uuid;

const TOKEN_PREFIX: &str = "sp_";
const TOKEN_BYTES: usize = 32;

pub struct IssuedSession {
    pub token: String,
    pub expires_at: DateTime<Utc>,
}

pub fn generate_token() -> String {
    let mut bytes = [0u8; TOKEN_BYTES];
    rand::thread_rng().fill_bytes(&mut bytes);
    format!("{TOKEN_PREFIX}{}", URL_SAFE_NO_PAD.encode(bytes))
}

pub fn hash_token(token: &str) -> String {
    hex::encode(Sha256::digest(token.as_bytes()))
}

pub async fn issue_session(db: &PgPool, user_id: Uuid, ttl: Duration) -> Result<IssuedSession> {
    let token = generate_token();
    let expires_at = Utc::now() + chrono::Duration::from_std(ttl)?;
    sqlx::query("INSERT INTO sessions (token_hash, user_id, expires_at) VALUES ($1, $2, $3)")
        .bind(hash_token(&token))
        .bind(user_id)
        .bind(expires_at)
        .execute(db)
        .await?;
    Ok(IssuedSession { token, expires_at })
}

pub async fn user_for_token(db: &PgPool, token: &str) -> Result<Option<Uuid>> {
    let row: Option<(Uuid,)> = sqlx::query_as(
        "UPDATE sessions SET last_used_at = now()
         WHERE token_hash = $1 AND expires_at > now()
         RETURNING user_id",
    )
    .bind(hash_token(token))
    .fetch_optional(db)
    .await?;
    Ok(row.map(|(user_id,)| user_id))
}

pub async fn revoke_session(db: &PgPool, token: &str) -> Result<()> {
    sqlx::query("DELETE FROM sessions WHERE token_hash = $1")
        .bind(hash_token(token))
        .execute(db)
        .await?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tokens_are_unique_and_hash_is_stable() {
        let a = generate_token();
        let b = generate_token();
        assert_ne!(a, b);
        assert!(a.starts_with("sp_"));
        assert_eq!(hash_token(&a), hash_token(&a));
        assert_ne!(hash_token(&a), a);
    }
}
