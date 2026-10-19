use std::collections::BTreeMap;
use std::sync::{Arc, Mutex};

use axum::body::Bytes;
use axum::extract::State;
use axum::http::{HeaderMap, Method, StatusCode, Uri};
use axum::response::{IntoResponse, Response};
use axum::routing::any;
use axum::Router;
use sha2::{Digest, Sha256};

#[derive(Default)]
pub struct Store {
    pub uploads: BTreeMap<String, BTreeMap<i32, Vec<u8>>>,
    pub objects: BTreeMap<String, Vec<u8>>,
    pub upload_keys: BTreeMap<String, String>,
}

#[derive(Clone, Default)]
pub struct FakeS3 {
    pub store: Arc<Mutex<Store>>,
}

fn query_param(uri: &Uri, name: &str) -> Option<String> {
    uri.query()?.split('&').find_map(|pair| {
        let (key, value) = pair.split_once('=').unwrap_or((pair, ""));
        (key == name).then(|| value.to_string())
    })
}

fn xml(body: String) -> Response {
    (StatusCode::OK, [("content-type", "application/xml")], body).into_response()
}

fn etag_of(data: &[u8]) -> String {
    format!("\"{}\"", hex::encode(&Sha256::digest(data)[..16]))
}

fn key_from(uri: &Uri) -> String {
    let path = uri.path().trim_start_matches('/');
    path.split_once('/')
        .map(|(_, key)| key.to_string())
        .unwrap_or_default()
}

async fn handle(
    State(fake): State<FakeS3>,
    method: Method,
    uri: Uri,
    _headers: HeaderMap,
    body: Bytes,
) -> Response {
    let key = key_from(&uri);
    let upload_id = query_param(&uri, "uploadId");
    let mut store = fake.store.lock().unwrap();
    match (method.as_str(), key.is_empty(), upload_id) {
        ("HEAD", true, _) => StatusCode::OK.into_response(),
        ("POST", false, None) if uri.query().is_some_and(|q| q.starts_with("uploads")) => {
            let id = format!("up-{}", store.uploads.len() + 1);
            store.uploads.insert(id.clone(), BTreeMap::new());
            store.upload_keys.insert(id.clone(), key.clone());
            xml(format!("<InitiateMultipartUploadResult><Bucket>b</Bucket><Key>{key}</Key><UploadId>{id}</UploadId></InitiateMultipartUploadResult>"))
        }
        ("PUT", false, Some(id)) => {
            let number: i32 = query_param(&uri, "partNumber")
                .and_then(|n| n.parse().ok())
                .unwrap_or(0);
            let etag = etag_of(&body);
            let Some(parts) = store.uploads.get_mut(&id) else {
                return StatusCode::NOT_FOUND.into_response();
            };
            parts.insert(number, body.to_vec());
            ([("etag", etag)], StatusCode::OK).into_response()
        }
        ("GET", false, Some(id)) => {
            let Some(parts) = store.uploads.get(&id) else {
                return StatusCode::NOT_FOUND.into_response();
            };
            let items: String = parts
                .iter()
                .map(|(n, data)| {
                    format!(
                        "<Part><PartNumber>{n}</PartNumber><ETag>{}</ETag><Size>{}</Size></Part>",
                        etag_of(data).replace('"', "&quot;"),
                        data.len()
                    )
                })
                .collect();
            xml(format!("<ListPartsResult><Bucket>b</Bucket><Key>{key}</Key><UploadId>{id}</UploadId><IsTruncated>false</IsTruncated>{items}</ListPartsResult>"))
        }
        ("POST", false, Some(id)) => {
            let Some(parts) = store.uploads.remove(&id) else {
                return StatusCode::NOT_FOUND.into_response();
            };
            let data: Vec<u8> = parts.into_values().flatten().collect();
            store.objects.insert(key.clone(), data);
            xml(format!("<CompleteMultipartUploadResult><Location>x</Location><Bucket>b</Bucket><Key>{key}</Key><ETag>&quot;done&quot;</ETag></CompleteMultipartUploadResult>"))
        }
        ("DELETE", false, Some(id)) => {
            store.uploads.remove(&id);
            StatusCode::NO_CONTENT.into_response()
        }
        ("DELETE", false, None) => {
            store.objects.remove(&key);
            StatusCode::NO_CONTENT.into_response()
        }
        ("HEAD", false, None) => match store.objects.get(&key) {
            Some(data) => {
                ([("content-length", data.len().to_string())], StatusCode::OK).into_response()
            }
            None => StatusCode::NOT_FOUND.into_response(),
        },
        ("GET", false, None) => match store.objects.get(&key) {
            Some(data) => (StatusCode::OK, data.clone()).into_response(),
            None => StatusCode::NOT_FOUND.into_response(),
        },
        _ => StatusCode::BAD_REQUEST.into_response(),
    }
}

impl FakeS3 {
    pub fn router(&self) -> Router {
        Router::new()
            .route("/{bucket}", any(handle))
            .route("/{bucket}/", any(handle))
            .route("/{bucket}/{*key}", any(handle))
            .layer(axum::extract::DefaultBodyLimit::disable())
            .with_state(self.clone())
    }

    pub fn put_object(&self, key: &str, data: Vec<u8>) {
        self.store
            .lock()
            .unwrap()
            .objects
            .insert(key.to_string(), data);
    }

    pub fn object(&self, key: &str) -> Option<Vec<u8>> {
        self.store.lock().unwrap().objects.get(key).cloned()
    }

    pub fn object_keys(&self) -> Vec<String> {
        self.store.lock().unwrap().objects.keys().cloned().collect()
    }
}
