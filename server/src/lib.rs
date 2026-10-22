pub mod answers;
pub mod assessments;
pub mod auth;
pub mod config;
pub mod db;
pub mod engine;
pub mod error;
pub mod findings;
pub mod finish;
pub mod health;
pub mod idempotency;
pub mod jobs;
pub mod live;
pub mod openapi;
pub mod photo_answers;
pub mod purge;
pub mod scans;
pub mod shares;
pub mod state;
pub mod storage;
pub mod uploads;
pub mod vision;
pub mod vision_cache;

use axum::extract::DefaultBodyLimit;
use axum::routing::{delete, get, post};
use axum::Router;
use tower_http::cors::{AllowOrigin, Any, CorsLayer};
use tower_http::trace::TraceLayer;

use state::AppState;

const JSON_BODY_LIMIT: usize = 8 * 1024 * 1024;

fn cors_layer(origins: &[String]) -> Option<CorsLayer> {
    if origins.is_empty() {
        return None;
    }
    let allowed: Vec<_> = origins.iter().filter_map(|o| o.parse().ok()).collect();
    Some(
        CorsLayer::new()
            .allow_origin(AllowOrigin::list(allowed))
            .allow_methods(Any)
            .allow_headers(Any),
    )
}

fn api_routes() -> Router<AppState> {
    Router::new()
        .route("/auth/register", post(auth::handlers::register))
        .route("/auth/login", post(auth::handlers::login))
        .route("/auth/apple", post(auth::handlers::apple_sign_in))
        .route("/auth/logout", post(auth::handlers::logout))
        .route(
            "/me",
            get(auth::handlers::me).delete(auth::handlers::delete_me),
        )
        .route("/openapi.json", get(openapi::serve_openapi))
        .route(
            "/scans",
            get(scans::handlers::list_scans).post(scans::handlers::create_scan),
        )
        .route(
            "/scans/{scan_id}",
            get(scans::handlers::get_scan)
                .patch(scans::handlers::update_scan)
                .delete(scans::handlers::delete_scan),
        )
        .route(
            "/scans/{scan_id}/assessment",
            get(scans::handlers::get_assessment),
        )
        .route("/scans/{scan_id}/scene", get(scans::handlers::get_scene))
        .route("/scans/{scan_id}/finish", post(finish::finish_scan))
        .route("/scans/{scan_id}/live", get(live::ws::live_socket))
        .route(
            "/scans/{scan_id}/live-ticket",
            post(live::tickets::create_live_ticket),
        )
        .route(
            "/scans/{scan_id}/artifacts",
            get(uploads::handlers::list_artifacts),
        )
        .merge(upload_routes())
        .merge(report_routes())
}

fn report_routes() -> Router<AppState> {
    Router::new()
        .route(
            "/scans/{scan_id}/answers",
            get(answers::list_answers).put(answers::save_answers),
        )
        .route(
            "/scans/{scan_id}/photo-answers",
            post(photo_answers::answer_from_photo),
        )
        .route(
            "/scans/{scan_id}/shares",
            get(shares::list_shares).post(shares::create_share),
        )
        .route(
            "/scans/{scan_id}/shares/{token}",
            delete(shares::delete_share),
        )
        .route("/shared/{token}", get(shares::get_shared_report))
}

fn upload_routes() -> Router<AppState> {
    Router::new()
        .route(
            "/scans/{scan_id}/uploads",
            post(uploads::handlers::create_upload),
        )
        .route(
            "/scans/{scan_id}/uploads/{upload_id}",
            get(uploads::handlers::upload_status),
        )
        .route(
            "/scans/{scan_id}/uploads/{upload_id}/parts",
            post(uploads::handlers::presign_parts),
        )
        .route(
            "/scans/{scan_id}/uploads/{upload_id}/complete",
            post(uploads::handlers::complete_upload),
        )
        .route(
            "/scans/{scan_id}/uploads/{upload_id}/abort",
            post(uploads::handlers::abort_upload),
        )
}

pub fn build_router(state: AppState) -> Router {
    let cors = cors_layer(&state.cfg.cors_origins);
    let router = Router::new()
        .route("/health", get(health::health))
        .route("/health/ready", get(health::ready))
        .nest("/v1", api_routes())
        .layer(DefaultBodyLimit::max(JSON_BODY_LIMIT))
        .layer(TraceLayer::new_for_http())
        .with_state(state);
    match cors {
        Some(cors) => router.layer(cors),
        None => router,
    }
}
