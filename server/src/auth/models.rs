use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use sqlx::FromRow;
use utoipa::ToSchema;
use uuid::Uuid;

#[derive(Clone, Debug, Serialize, FromRow, ToSchema)]
pub struct User {
    pub id: Uuid,
    pub email: Option<String>,
}

#[derive(Deserialize, ToSchema)]
pub struct Credentials {
    pub email: String,
    pub password: String,
}

#[derive(Deserialize, ToSchema)]
pub struct AppleSignIn {
    pub identity_token: String,
    pub nonce: Option<String>,
}

#[derive(Serialize, ToSchema)]
pub struct AuthResponse {
    pub token: String,
    pub expires_at: DateTime<Utc>,
    pub user: User,
}
