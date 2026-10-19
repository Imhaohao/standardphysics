use anyhow::{anyhow, Result};
use argon2::password_hash::rand_core::OsRng;
use argon2::password_hash::{PasswordHash, PasswordHasher, PasswordVerifier, SaltString};
use argon2::Argon2;
use std::sync::OnceLock;

pub const MIN_PASSWORD_LEN: usize = 8;
pub const MAX_PASSWORD_LEN: usize = 256;

pub fn hash_password_blocking(password: &str) -> Result<String> {
    let salt = SaltString::generate(&mut OsRng);
    let hash = Argon2::default()
        .hash_password(password.as_bytes(), &salt)
        .map_err(|e| anyhow!("password hashing failed: {e}"))?;
    Ok(hash.to_string())
}

pub fn verify_password_blocking(password: &str, stored_hash: &str) -> bool {
    let Ok(parsed) = PasswordHash::new(stored_hash) else {
        return false;
    };
    Argon2::default()
        .verify_password(password.as_bytes(), &parsed)
        .is_ok()
}

fn dummy_hash() -> &'static str {
    static DUMMY: OnceLock<String> = OnceLock::new();
    DUMMY.get_or_init(|| {
        hash_password_blocking("dummy password for unknown accounts")
            .expect("hashing a fixed password cannot fail")
    })
}

/// Runs a full argon2 verification against a throwaway hash so unknown accounts cost
/// the same as wrong passwords.
pub async fn verify_against_dummy(password: String) -> Result<()> {
    tokio::task::spawn_blocking(move || verify_password_blocking(&password, dummy_hash())).await?;
    Ok(())
}

pub async fn hash_password(password: String) -> Result<String> {
    tokio::task::spawn_blocking(move || hash_password_blocking(&password)).await?
}

pub async fn verify_password(password: String, stored_hash: String) -> Result<bool> {
    Ok(
        tokio::task::spawn_blocking(move || verify_password_blocking(&password, &stored_hash))
            .await?,
    )
}

pub fn password_is_acceptable(password: &str) -> bool {
    (MIN_PASSWORD_LEN..=MAX_PASSWORD_LEN).contains(&password.len())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hash_verifies_only_for_the_right_password() {
        let hash = hash_password_blocking("correct horse").unwrap();
        assert!(verify_password_blocking("correct horse", &hash));
        assert!(!verify_password_blocking("wrong horse", &hash));
    }

    #[test]
    fn dummy_hash_is_a_real_hash_with_the_same_cost_as_real_ones() {
        let real = hash_password_blocking("correct horse").unwrap();
        let (dummy, real) = (dummy_hash(), real.as_str());
        let cost = |hash: &str| {
            let parsed = PasswordHash::new(hash).unwrap();
            (parsed.algorithm.to_string(), parsed.params.to_string())
        };
        assert_eq!(cost(dummy), cost(real));
        assert!(!verify_password_blocking("anything", dummy));
    }

    #[tokio::test]
    async fn verifying_against_the_dummy_succeeds_quietly() {
        verify_against_dummy("whatever".into()).await.unwrap();
    }

    #[test]
    fn garbage_hash_never_verifies() {
        assert!(!verify_password_blocking("x", "not-a-hash"));
    }
}
