use axum::extract::FromRequestParts;
use axum::http::header::AUTHORIZATION;
use axum::http::request::Parts;
use axum::http::HeaderMap;
use uuid::Uuid;

use super::session::user_for_token;
use crate::error::ApiError;
use crate::state::AppState;

#[derive(Clone, Copy, Debug)]
pub struct AuthUser(pub Uuid);

pub struct BearerToken(pub String);

pub fn bearer_from_headers(headers: &HeaderMap) -> Option<String> {
    let value = headers.get(AUTHORIZATION)?.to_str().ok()?;
    let token = value.strip_prefix("Bearer ")?;
    Some(token.trim().to_string())
}

pub async fn authenticate(state: &AppState, token: &str) -> Result<Uuid, ApiError> {
    user_for_token(&state.db, token)
        .await?
        .ok_or(ApiError::Unauthorized)
}

impl FromRequestParts<AppState> for AuthUser {
    type Rejection = ApiError;

    async fn from_request_parts(
        parts: &mut Parts,
        state: &AppState,
    ) -> Result<Self, Self::Rejection> {
        let token = bearer_from_headers(&parts.headers).ok_or(ApiError::Unauthorized)?;
        Ok(AuthUser(authenticate(state, &token).await?))
    }
}

impl FromRequestParts<AppState> for BearerToken {
    type Rejection = ApiError;

    async fn from_request_parts(
        parts: &mut Parts,
        _state: &AppState,
    ) -> Result<Self, Self::Rejection> {
        bearer_from_headers(&parts.headers)
            .map(BearerToken)
            .ok_or(ApiError::Unauthorized)
    }
}
