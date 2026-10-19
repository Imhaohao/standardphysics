use axum::extract::ws::{CloseCode, Message, WebSocket, WebSocketUpgrade};
use axum::extract::{Path, Query, State};
use axum::http::HeaderMap;
use axum::response::Response;
use serde::Deserialize;
use tokio::sync::broadcast::error::RecvError;
use uuid::Uuid;

use super::hub::LiveSession;
use super::protocol::{validate_update, ClientMessage, RoomUpdate, ServerMessage};
use super::rooms::{scan_accepts_updates, upsert_room};
use super::tickets::consume_ticket;
use crate::auth::extractor::{authenticate, bearer_from_headers};
use crate::error::{ApiError, ApiResult};
use crate::scans::repo::get_owned_scan;
use crate::state::AppState;

const MAX_MESSAGE_BYTES: usize = 32 * 1024 * 1024;
const CLOSE_INTERNAL: CloseCode = 1011;

#[derive(Deserialize)]
pub struct LiveQuery {
    pub ticket: Option<String>,
    pub role: Option<String>,
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum Role {
    Writer,
    Viewer,
}

fn role_from(query: &LiveQuery) -> Role {
    match query.role.as_deref() {
        Some("viewer") => Role::Viewer,
        _ => Role::Writer,
    }
}

#[utoipa::path(
    get, path = "/v1/scans/{scan_id}/live", tag = "live",
    security(("bearer" = [])),
    params(
        ("scan_id" = Uuid, Path),
        ("ticket" = Option<String>, Query, description = "Single-use ticket from POST /v1/scans/{scan_id}/live-ticket, for browsers that cannot set an Authorization header. Session tokens are never accepted in the query string."),
        ("role" = Option<String>, Query, description = "`viewer` for a read-only subscription"),
    ),
    responses((status = 101, description = "WebSocket upgrade. Client sends ClientMessage JSON text frames, server sends ServerMessage."))
)]
pub async fn live_socket(
    State(state): State<AppState>,
    Path(scan_id): Path<Uuid>,
    Query(query): Query<LiveQuery>,
    headers: HeaderMap,
    upgrade: WebSocketUpgrade,
) -> ApiResult<Response> {
    let user_id = socket_user(&state, &headers, &query, scan_id).await?;
    get_owned_scan(&state.db, user_id, scan_id).await?;
    let role = role_from(&query);
    Ok(upgrade
        .max_message_size(MAX_MESSAGE_BYTES)
        .on_upgrade(move |socket| run_connection(state, scan_id, role, socket)))
}

async fn socket_user(
    state: &AppState,
    headers: &HeaderMap,
    query: &LiveQuery,
    scan_id: Uuid,
) -> ApiResult<Uuid> {
    if let Some(token) = bearer_from_headers(headers) {
        return authenticate(state, &token).await;
    }
    let ticket = query.ticket.as_deref().ok_or(ApiError::Unauthorized)?;
    consume_ticket(&state.db, ticket, scan_id)
        .await?
        .ok_or(ApiError::Unauthorized)
}

async fn send(socket: &mut WebSocket, message: &ServerMessage) -> bool {
    let Ok(text) = serde_json::to_string(message) else {
        return false;
    };
    socket.send(Message::Text(text.into())).await.is_ok()
}

async fn run_connection(state: AppState, scan_id: Uuid, role: Role, mut socket: WebSocket) {
    let session = match state.hub.session(&state.db, scan_id).await {
        Ok(session) => session,
        Err(err) => {
            tracing::error!(error = ?err, %scan_id, "could not open live session");
            let _ = send(
                &mut socket,
                &ServerMessage::error("live session unavailable"),
            )
            .await;
            let _ = socket
                .send(Message::Close(Some(axum::extract::ws::CloseFrame {
                    code: CLOSE_INTERNAL,
                    reason: "unavailable".into(),
                })))
                .await;
            return;
        }
    };
    serve_socket(&state, &session, role, &mut socket).await;
    state.hub.release(scan_id).await;
}

async fn serve_socket(state: &AppState, session: &LiveSession, role: Role, socket: &mut WebSocket) {
    let mut updates = session.subscribe();
    if !send(socket, &session.snapshot()).await {
        return;
    }
    if let Some(scene) = session.scene_message() {
        if !send(socket, &scene).await {
            return;
        }
    }
    loop {
        let keep_going = tokio::select! {
            incoming = socket.recv() => handle_incoming(state, session, role, socket, incoming).await,
            outgoing = updates.recv() => forward_update(session, socket, outgoing).await,
        };
        if !keep_going {
            return;
        }
    }
}

async fn forward_update(
    session: &LiveSession,
    socket: &mut WebSocket,
    outgoing: Result<ServerMessage, RecvError>,
) -> bool {
    match outgoing {
        Ok(message) => send(socket, &message).await,
        Err(RecvError::Lagged(_)) => send(socket, &session.snapshot()).await,
        Err(RecvError::Closed) => false,
    }
}

async fn handle_incoming(
    state: &AppState,
    session: &LiveSession,
    role: Role,
    socket: &mut WebSocket,
    incoming: Option<Result<Message, axum::Error>>,
) -> bool {
    match incoming {
        Some(Ok(Message::Text(text))) => {
            let reply = handle_text(state, session, role, text.as_str()).await;
            match reply {
                Some(message) => send(socket, &message).await,
                None => true,
            }
        }
        Some(Ok(Message::Binary(_))) => {
            send(
                socket,
                &ServerMessage::error("binary frames are not supported"),
            )
            .await
        }
        Some(Ok(Message::Close(_))) | None | Some(Err(_)) => false,
        Some(Ok(_)) => true,
    }
}

async fn handle_text(
    state: &AppState,
    session: &LiveSession,
    role: Role,
    text: &str,
) -> Option<ServerMessage> {
    let message: ClientMessage = match serde_json::from_str(text) {
        Ok(message) => message,
        Err(err) => return Some(ServerMessage::error(format!("invalid message: {err}"))),
    };
    match message {
        ClientMessage::Ping => Some(ServerMessage::Pong),
        ClientMessage::Room(_) if role == Role::Viewer => {
            Some(ServerMessage::error("this connection is read-only"))
        }
        ClientMessage::Room(update) => accept_room_update(state, session, update).await,
    }
}

async fn accept_room_update(
    state: &AppState,
    session: &LiveSession,
    update: RoomUpdate,
) -> Option<ServerMessage> {
    match process_room_update(state, session, update).await {
        Ok(messages) => {
            messages
                .into_iter()
                .for_each(|message| session.publish(message));
            None
        }
        Err(message) => Some(ServerMessage::error(message)),
    }
}

async fn process_room_update(
    state: &AppState,
    session: &LiveSession,
    update: RoomUpdate,
) -> Result<Vec<ServerMessage>, String> {
    validate_update(&update)?;
    let scan_id = session.scan_id();
    match scan_accepts_updates(&state.db, scan_id).await {
        Ok(true) => {}
        Ok(false) => return Err("scan is no longer accepting updates".to_string()),
        Err(err) => return Err(internal_message(&err)),
    }
    upsert_room(&state.db, scan_id, &update)
        .await
        .map_err(|err| internal_message(&err))?;
    session
        .apply_update(update)
        .await
        .map_err(|err| internal_message(&err))
}

fn internal_message(err: &anyhow::Error) -> String {
    tracing::error!(error = ?err, "live update failed");
    "could not process update".to_string()
}
