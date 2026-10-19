use anyhow::Result;

use super::queue::Job;
use super::worker::JobContext;

pub async fn texture_bake(_ctx: JobContext, job: Job) -> Result<()> {
    tracing::info!(
        job_id = %job.id,
        scan_id = %job.payload["scan_id"],
        "texture_bake is a stub until the GPU worker exists"
    );
    Ok(())
}
