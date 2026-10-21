use utoipa::openapi::security::{HttpAuthScheme, HttpBuilder, SecurityScheme};
use utoipa::{Modify, OpenApi};

use crate::{answers, auth, finish, health, live, photo_answers, scans, shares, uploads};

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
        description = "Scans, uploads, live findings and assessments.\n\nUploads: artifact kind `mesh` carries the binary `mesh.spm`; `crop` carries detector crops (JPEG); `photo`, `video` and `other` are free-form. `room` carries one RoomPlan CapturedRoom JSON document (`application/json`, at most 16 MiB) and is the offline-safe path for rooms: on `complete` it is parsed and applied to the scan exactly like a live `room` message (room id = the CapturedRoom `identifier`, falling back to the filename stem; final; the same room id arriving by socket and by upload replaces, never duplicates), and it is included at finish. A room upload is rejected with 409 once the scan is no longer capturing and with 422 (object discarded) if it is not a valid CapturedRoom. Rooms may also stream live over the WebSocket (`GET /v1/scans/{scan_id}/live`, JSON text frames). Client frames are `ClientMessage` (`room`, `ping`); server frames are `ServerMessage` (`hello`, `scene` (merged Scene, sent after hello and after finish), `room` (one converted sp-core Room, on every room update), `findings`, `report`, `error`, `pong`). Both are defined under components/schemas.\n\nAuth for the socket: native clients send `Authorization: Bearer`; browsers call `POST /v1/scans/{scan_id}/live-ticket` and open the socket with the single-use `?ticket=` (valid 30 s). Session tokens in the query string are rejected.\n\nPresigned upload URLs all point at one host, returned as `host` in the presign response and equal to the host of `S3_PUBLIC_ENDPOINT` (https, path-style: `https://<host>/<bucket>/<key>?X-Amz-...`). Allowlist that host on the device.\n\nApple sign-in: send the raw `nonce`; the identity token's `nonce` claim must be its lowercase hex SHA-256.\n\n`POST /v1/scans` and `POST /v1/scans/{scan_id}/uploads` accept `Idempotency-Key`.",
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
        auth::handlers::delete_me,
        scans::handlers::create_scan,
        scans::handlers::list_scans,
        scans::handlers::get_scan,
        scans::handlers::get_assessment,
        scans::handlers::get_scene,
        scans::handlers::update_scan,
        scans::handlers::delete_scan,
        answers::list_answers,
        answers::save_answers,
        photo_answers::answer_from_photo,
        shares::create_share,
        shares::list_shares,
        shares::delete_share,
        shares::get_shared_report,
        finish::finish_scan,
        uploads::handlers::create_upload,
        uploads::handlers::upload_status,
        uploads::handlers::presign_parts,
        uploads::handlers::complete_upload,
        uploads::handlers::abort_upload,
        uploads::handlers::list_artifacts,
        live::tickets::create_live_ticket,
        live::ws::live_socket,
    ),
    components(schemas(
        live::protocol::ClientMessage,
        live::protocol::ServerMessage,
        live::protocol::RoomUpdate,
        crate::findings::Severity,
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
