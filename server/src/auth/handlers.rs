use axum::extract::State;
use axum::http::StatusCode;
use axum::Json;

use super::extractor::{AuthUser, BearerToken};
use super::models::{AppleSignIn, AuthResponse, Credentials, User};
use super::password::{
    hash_password, password_is_acceptable, verify_against_dummy, verify_password,
};
use super::repo::{self, NewUser};
use super::session::{issue_session, revoke_session};
use crate::error::{ApiError, ApiResult, ErrorBody};
use crate::state::AppState;

async fn respond_with_session(state: &AppState, user: User) -> ApiResult<AuthResponse> {
    let session = issue_session(&state.db, user.id, state.cfg.session_ttl).await?;
    Ok(AuthResponse {
        token: session.token,
        expires_at: session.expires_at,
        user,
    })
}

fn normalized_email(raw: &str) -> ApiResult<String> {
    let email = raw.trim().to_lowercase();
    let looks_valid = email.len() <= 254
        && email
            .split_once('@')
            .is_some_and(|(local, domain)| !local.is_empty() && domain.contains('.'));
    if !looks_valid {
        return Err(ApiError::bad_request("email address is not valid"));
    }
    Ok(email)
}

#[utoipa::path(
    post, path = "/v1/auth/register", tag = "auth",
    request_body = Credentials,
    responses(
        (status = 201, body = AuthResponse),
        (status = 400, body = ErrorBody),
        (status = 409, body = ErrorBody),
    )
)]
pub async fn register(
    State(state): State<AppState>,
    Json(body): Json<Credentials>,
) -> ApiResult<(StatusCode, Json<AuthResponse>)> {
    let email = normalized_email(&body.email)?;
    if !password_is_acceptable(&body.password) {
        return Err(ApiError::bad_request(
            "password must be 8 to 256 characters",
        ));
    }
    let hash = hash_password(body.password).await?;
    match repo::insert_email_user(&state.db, &email, &hash).await? {
        NewUser::EmailTaken => Err(ApiError::Conflict("email is already registered".into())),
        NewUser::Created(user) => {
            let response = respond_with_session(&state, user).await?;
            Ok((StatusCode::CREATED, Json(response)))
        }
    }
}

#[utoipa::path(
    post, path = "/v1/auth/login", tag = "auth",
    request_body = Credentials,
    responses((status = 200, body = AuthResponse), (status = 401, body = ErrorBody))
)]
pub async fn login(
    State(state): State<AppState>,
    Json(body): Json<Credentials>,
) -> ApiResult<Json<AuthResponse>> {
    let found = repo::find_credentials(&state.db, body.email.trim()).await?;
    let Some((user, hash)) = found else {
        verify_against_dummy(body.password).await?;
        return Err(ApiError::Unauthorized);
    };
    if !verify_password(body.password, hash).await? {
        return Err(ApiError::Unauthorized);
    }
    Ok(Json(respond_with_session(&state, user).await?))
}

#[utoipa::path(
    post, path = "/v1/auth/apple", tag = "auth",
    request_body = AppleSignIn,
    responses((status = 200, body = AuthResponse), (status = 401, body = ErrorBody))
)]
pub async fn apple_sign_in(
    State(state): State<AppState>,
    Json(body): Json<AppleSignIn>,
) -> ApiResult<Json<AuthResponse>> {
    if !state.apple.is_configured() {
        return Err(ApiError::bad_request("apple sign-in is not configured"));
    }
    if body.nonce.is_empty() {
        return Err(ApiError::bad_request("nonce is required"));
    }
    let identity = state
        .apple
        .verify(&body.identity_token, &body.nonce)
        .await
        .map_err(|err| {
            tracing::warn!(error = %err, "apple identity token rejected");
            ApiError::Unauthorized
        })?;
    let user =
        repo::upsert_apple_user(&state.db, &identity.subject, identity.email.as_deref()).await?;
    Ok(Json(respond_with_session(&state, user).await?))
}

#[utoipa::path(
    post, path = "/v1/auth/logout", tag = "auth",
    security(("bearer" = [])),
    responses((status = 204), (status = 401, body = ErrorBody))
)]
pub async fn logout(
    State(state): State<AppState>,
    _user: AuthUser,
    BearerToken(token): BearerToken,
) -> ApiResult<StatusCode> {
    revoke_session(&state.db, &token).await?;
    Ok(StatusCode::NO_CONTENT)
}

#[utoipa::path(
    get, path = "/v1/me", tag = "auth",
    security(("bearer" = [])),
    responses((status = 200, body = User), (status = 401, body = ErrorBody))
)]
pub async fn me(
    State(state): State<AppState>,
    AuthUser(user_id): AuthUser,
) -> ApiResult<Json<User>> {
    let user = repo::find_user(&state.db, user_id)
        .await?
        .ok_or(ApiError::Unauthorized)?;
    Ok(Json(user))
}

#[utoipa::path(
    delete, path = "/v1/me", tag = "auth",
    security(("bearer" = [])),
    responses((status = 204, description = "The account, its sessions, scans and uploaded files are gone"), (status = 401, body = ErrorBody))
)]
pub async fn delete_me(
    State(state): State<AppState>,
    AuthUser(user_id): AuthUser,
) -> ApiResult<StatusCode> {
    crate::purge::delete_user(&state.db, &state.storage, user_id).await?;
    Ok(StatusCode::NO_CONTENT)
}
