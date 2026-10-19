use std::collections::{BTreeMap, HashMap};
use std::sync::{Arc, Mutex, MutexGuard};
use std::time::Instant;

use anyhow::{anyhow, Result};
use sqlx::PgPool;
use tokio::sync::broadcast;
use uuid::Uuid;

use super::protocol::{RoomUpdate, ServerMessage};
use super::rooms::{load_rooms, RoomState};
use crate::engine::{SceneEngine, UpdatedRoom};
use crate::findings::{summarize, Finding};

const BROADCAST_CAPACITY: usize = 256;

struct SessionState {
    engine: SceneEngine,
    rooms: BTreeMap<String, RoomState>,
}

impl SessionState {
    fn new() -> Result<Self> {
        Ok(Self {
            engine: SceneEngine::new()?,
            rooms: BTreeMap::new(),
        })
    }

    fn apply(&mut self, update: &RoomUpdate) -> Result<UpdatedRoom> {
        let room = self
            .rooms
            .entry(update.room_id.clone())
            .or_insert_with(|| RoomState::new(&update.room_id));
        room.apply(update);
        self.engine.update_room(room.to_input())
    }

    fn all_findings(&self) -> Vec<Finding> {
        self.engine.all_findings()
    }

    fn restore(&mut self, rooms: Vec<RoomState>) -> Result<()> {
        for room in rooms {
            self.engine.update_room(room.to_input())?;
            self.rooms.insert(room.room_id.clone(), room);
        }
        Ok(())
    }
}

pub struct LiveSession {
    scan_id: Uuid,
    state: Arc<Mutex<SessionState>>,
    tx: broadcast::Sender<ServerMessage>,
}

fn lock(state: &Mutex<SessionState>) -> MutexGuard<'_, SessionState> {
    state
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
}

impl LiveSession {
    fn new(scan_id: Uuid, state: SessionState) -> Self {
        let (tx, _) = broadcast::channel(BROADCAST_CAPACITY);
        Self {
            scan_id,
            state: Arc::new(Mutex::new(state)),
            tx,
        }
    }

    pub fn scan_id(&self) -> Uuid {
        self.scan_id
    }

    pub fn subscribe(&self) -> broadcast::Receiver<ServerMessage> {
        self.tx.subscribe()
    }

    pub fn publish(&self, message: ServerMessage) {
        let _ = self.tx.send(message);
    }

    pub fn snapshot(&self) -> ServerMessage {
        let state = lock(&self.state);
        let findings = state.all_findings();
        ServerMessage::Hello {
            scan_id: self.scan_id,
            rooms: state.rooms.keys().cloned().collect(),
            summary: summarize(&findings),
            findings,
        }
    }

    pub fn scene_message(&self) -> Option<ServerMessage> {
        let scene = lock(&self.state).engine.scene_json().ok().flatten()?;
        Some(ServerMessage::Scene { scene })
    }

    pub async fn apply_update(&self, update: RoomUpdate) -> Result<Vec<ServerMessage>> {
        let state = Arc::clone(&self.state);
        tokio::task::spawn_blocking(move || {
            let started = Instant::now();
            let mut state = lock(&state);
            let updated = state.apply(&update)?;
            let findings = ServerMessage::Findings {
                room_id: update.room_id,
                seq: update.seq,
                finalized: update.finalized,
                findings: updated.findings,
                summary: summarize(&state.all_findings()),
                elapsed_ms: started.elapsed().as_millis() as u64,
            };
            let room = updated.room.map(|room| ServerMessage::Room { room });
            Ok::<_, anyhow::Error>(room.into_iter().chain([findings]).collect())
        })
        .await
        .map_err(|e| anyhow!("engine task failed: {e}"))?
    }
}

#[derive(Default)]
pub struct LiveHub {
    sessions: tokio::sync::Mutex<HashMap<Uuid, Arc<LiveSession>>>,
}

impl LiveHub {
    pub async fn session(&self, db: &PgPool, scan_id: Uuid) -> Result<Arc<LiveSession>> {
        let mut sessions = self.sessions.lock().await;
        if let Some(existing) = sessions.get(&scan_id) {
            return Ok(Arc::clone(existing));
        }
        let rooms = load_rooms(db, scan_id).await?;
        let session = tokio::task::spawn_blocking(move || -> Result<LiveSession> {
            let mut state = SessionState::new()?;
            state.restore(rooms)?;
            Ok(LiveSession::new(scan_id, state))
        })
        .await??;
        let session = Arc::new(session);
        sessions.insert(scan_id, Arc::clone(&session));
        Ok(session)
    }

    pub async fn peek(&self, scan_id: Uuid) -> Option<Arc<LiveSession>> {
        self.sessions.lock().await.get(&scan_id).cloned()
    }

    pub async fn release(&self, scan_id: Uuid) {
        let mut sessions = self.sessions.lock().await;
        let idle = sessions
            .get(&scan_id)
            .is_some_and(|s| s.tx.receiver_count() == 0);
        if idle {
            sessions.remove(&scan_id);
        }
    }
}
