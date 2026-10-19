use anyhow::Result;
use sqlx::PgPool;
use uuid::Uuid;

use super::models::User;

pub enum NewUser {
    Created(User),
    EmailTaken,
}

pub async fn insert_email_user(db: &PgPool, email: &str, password_hash: &str) -> Result<NewUser> {
    let inserted: Option<User> = sqlx::query_as(
        "INSERT INTO users (id, email, password_hash) VALUES ($1, $2, $3)
         ON CONFLICT DO NOTHING
         RETURNING id, email",
    )
    .bind(Uuid::new_v4())
    .bind(email)
    .bind(password_hash)
    .fetch_optional(db)
    .await?;
    Ok(inserted.map_or(NewUser::EmailTaken, NewUser::Created))
}

pub async fn find_credentials(db: &PgPool, email: &str) -> Result<Option<(User, String)>> {
    let row: Option<(Uuid, Option<String>, Option<String>)> =
        sqlx::query_as("SELECT id, email, password_hash FROM users WHERE lower(email) = lower($1)")
            .bind(email)
            .fetch_optional(db)
            .await?;
    Ok(row.and_then(|(id, email, hash)| Some((User { id, email }, hash?))))
}

pub async fn upsert_apple_user(db: &PgPool, subject: &str, email: Option<&str>) -> Result<User> {
    let user = sqlx::query_as(
        "INSERT INTO users (id, apple_sub, email) VALUES ($1, $2, $3)
         ON CONFLICT (apple_sub) WHERE apple_sub IS NOT NULL
         DO UPDATE SET email = COALESCE(users.email, EXCLUDED.email)
         RETURNING id, email",
    )
    .bind(Uuid::new_v4())
    .bind(subject)
    .bind(email)
    .fetch_one(db)
    .await?;
    Ok(user)
}

pub async fn find_user(db: &PgPool, id: Uuid) -> Result<Option<User>> {
    let user = sqlx::query_as("SELECT id, email FROM users WHERE id = $1")
        .bind(id)
        .fetch_optional(db)
        .await?;
    Ok(user)
}
