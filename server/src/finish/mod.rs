pub mod labelling;
pub mod pipeline;
pub mod relabel;

use axum::extract::{Path, State};
use axum::Json;
use uuid::Uuid;

use crate::auth::AuthUser;
use crate::error::{ApiError, ApiResult, ErrorBody};
use crate::scans::models::Report;
use crate::scans::repo::{get_owned_scan, set_status};
use crate::state::AppState;

const STUCK_FINISH_MINUTES: i32 = 5;

async fn begin_finish(state: &AppState, scan_id: Uuid) -> ApiResult<()> {
    let claimed = sqlx::query(
        "UPDATE scans SET status = 'finishing', updated_at = now()
         WHERE id = $1
           AND (status <> 'finishing' OR updated_at < now() - make_interval(mins => $2))",
    )
    .bind(scan_id)
    .bind(STUCK_FINISH_MINUTES)
    .execute(&state.db)
    .await?;
    if claimed.rows_affected() == 0 {
        return Err(ApiError::Conflict("scan is already being finished".into()));
    }
    Ok(())
}

#[utoipa::path(
    post, path = "/v1/scans/{scan_id}/finish", tag = "scans",
    security(("bearer" = [])),
    params(("scan_id" = Uuid, Path)),
    responses(
        (status = 200, body = Report),
        (status = 404, body = ErrorBody),
        (status = 409, body = ErrorBody),
    )
)]
pub async fn finish_scan(
    State(state): State<AppState>,
    AuthUser(user_id): AuthUser,
    Path(scan_id): Path<Uuid>,
) -> ApiResult<Json<Report>> {
    get_owned_scan(&state.db, user_id, scan_id).await?;
    begin_finish(&state, scan_id).await?;
    let report = match pipeline::run_finish(&state, scan_id).await {
        Ok(report) => report,
        Err(err) => {
            set_status(&state.db, scan_id, "failed").await?;
            return Err(err.into());
        }
    };
    set_status(&state.db, scan_id, "complete").await?;
    if let Err(err) = pipeline::after_finish(&state, &report).await {
        tracing::error!(error = ?err, %scan_id, "post-finish steps failed");
    }
    Ok(Json(report))
}
