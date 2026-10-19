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
        description = "Scans, uploads, live findings and assessments.\n\nUploads: artifact kind `mesh` carries the binary `mesh.spm`; `crop` carries detector crops (JPEG); `photo`, `video` and `other` are free-form. RoomPlan rooms are not uploaded as files: they stream as CapturedRoom JSON per room over the live WebSocket (`GET /v1/scans/{scan_id}/live`, JSON text frames). Client frames are `ClientMessage` (`room`, `ping`); server frames are `ServerMessage` (`hello`, `scene` (merged Scene, sent after hello and after finish), `room` (one converted sp-core Room, on every room update), `findings`, `report`, `error`, `pong`). Both are defined under components/schemas.",
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
        scans::handlers::get_scene,
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
