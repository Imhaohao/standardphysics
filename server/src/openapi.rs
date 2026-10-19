use utoipa::openapi::security::{HttpAuthScheme, HttpBuilder, SecurityScheme};
use utoipa::{Modify, OpenApi};

use crate::{auth, finish, health, live, scans, uploads};

struct BearerAuth;

impl Modify for BearerAuth {
    fn modify(&self, openapi: &mut utoipa::openapi::OpenApi) {
        let components = openapi.components.get_or_insert_with(Default::default);
        components.add_security_scheme(
            "bearer",
            SecurityScheme::Http(HttpBuilder::new().scheme(HttpAuthScheme::Bearer).build()),
        );
    }
}

#[derive(OpenApi)]
#[openapi(
    info(
        title = "Standard Physics server",
        description = "Scans, uploads, live findings and assessments.",
        version = "1.0.0"
    ),
    paths(
        health::health,
        health::ready,
        auth::handlers::register,
        auth::handlers::login,
        auth::handlers::apple_sign_in,
        auth::handlers::logout,
        auth::handlers::me,
        scans::handlers::create_scan,
        scans::handlers::list_scans,
        scans::handlers::get_scan,
        scans::handlers::get_assessment,
        finish::finish_scan,
        uploads::handlers::create_upload,
        uploads::handlers::upload_status,
        uploads::handlers::presign_parts,
        uploads::handlers::complete_upload,
        uploads::handlers::abort_upload,
        uploads::handlers::list_artifacts,
        live::ws::live_socket,
    ),
    components(schemas(
        live::protocol::ClientMessage,
        live::protocol::ServerMessage,
        live::protocol::RoomUpdate,
    )),
    modifiers(&BearerAuth)
)]
pub struct ApiDoc;

pub fn openapi_json() -> String {
    ApiDoc::openapi()
        .to_pretty_json()
        .expect("openapi spec serialises")
}

pub async fn serve_openapi() -> axum::Json<utoipa::openapi::OpenApi> {
    axum::Json(ApiDoc::openapi())
}
