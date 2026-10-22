//! Vision replies keyed by a hash of the image bytes, the model and the question. The same
//! photo asked the same thing never goes to the model twice, across finishes, re-assessments,
//! resumed scans and users.

use std::collections::HashMap;

use anyhow::Result;
use serde_json::Value;
use sha2::{Digest, Sha256};
use sqlx::types::Json;
use sqlx::PgPool;

/// One hash over every part that could change the reply.
pub fn cache_key(parts: &[&str]) -> String {
    let mut hasher = Sha256::new();
    for part in parts {
        hasher.update((part.len() as u64).to_le_bytes());
        hasher.update(part.as_bytes());
    }
    hex::encode(hasher.finalize())
}

pub async fn lookup(db: &PgPool, keys: &[String]) -> Result<HashMap<String, Value>> {
    if keys.is_empty() {
        return Ok(HashMap::new());
    }
    let rows: Vec<(String, Json<Value>)> =
        sqlx::query_as("SELECT key, reply FROM vision_cache WHERE key = ANY($1)")
            .bind(keys)
            .fetch_all(db)
            .await?;
    Ok(rows
        .into_iter()
        .map(|(key, reply)| (key, reply.0))
        .collect())
}

pub async fn store(db: &PgPool, entries: &[(String, Value)]) -> Result<()> {
    for (key, reply) in entries {
        sqlx::query(
            "INSERT INTO vision_cache (key, reply) VALUES ($1, $2)
             ON CONFLICT (key) DO NOTHING",
        )
        .bind(key)
        .bind(Json(reply))
        .execute(db)
        .await?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn keys_separate_their_parts() {
        assert_ne!(cache_key(&["ab", "c"]), cache_key(&["a", "bc"]));
        assert_eq!(cache_key(&["x", "y"]), cache_key(&["x", "y"]));
    }
}
