use std::collections::HashMap;
use std::sync::Arc;
use std::time::Duration;

use anyhow::{anyhow, Context, Result};
use base64::engine::general_purpose::STANDARD;
use base64::Engine;
use serde::Deserialize;
use serde_json::{json, Value};
use tokio::sync::Semaphore;
use tokio::task::JoinSet;
use tokio::time::Instant;

use crate::config::LabelConfig;
use crate::storage::Storage;

const SYSTEM_PROMPT: &str = "You label cropped photos of objects found in commercial interiors \
for an accessibility inspection. Reply with a JSON object {\"category\": <one of the allowed \
categories>, \"confidence\": <number between 0 and 1>} and nothing else.";

#[derive(Clone, Debug)]
pub struct LabelRequest {
    pub observation_id: String,
    pub crop_key: String,
    pub content_type: String,
    pub image_sha256: String,
}

#[derive(Clone, Debug, PartialEq)]
pub struct LabelResult {
    pub observation_id: String,
    pub category: String,
    pub confidence: f64,
}

#[derive(Debug, Default)]
pub struct LabelOutcome {
    pub labelled: Vec<LabelResult>,
    pub unlabelled: Vec<String>,
    pub deadline_hit: bool,
}

#[derive(Deserialize)]
struct ChatResponse {
    choices: Vec<ChatChoice>,
}

#[derive(Deserialize)]
struct ChatChoice {
    message: ChatMessage,
}

#[derive(Deserialize)]
struct ChatMessage {
    content: String,
}

#[derive(Clone)]
pub struct Labeller {
    cfg: LabelConfig,
    http: reqwest::Client,
}

pub fn build_request_body(model: &str, categories: &[String], data_uri: &str) -> Value {
    json!({
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": [
                {"type": "text", "text": format!("Allowed categories: {}", categories.join(", "))},
                {"type": "image_url", "image_url": {"url": data_uri}},
            ]},
        ],
    })
}

fn strip_code_fence(content: &str) -> &str {
    let trimmed = content.trim();
    let without_open = trimmed
        .strip_prefix("```json")
        .or_else(|| trimmed.strip_prefix("```"))
        .unwrap_or(trimmed);
    without_open
        .strip_suffix("```")
        .unwrap_or(without_open)
        .trim()
}

pub fn parse_label(content: &str, categories: &[String]) -> Result<(String, f64)> {
    let value: Value =
        serde_json::from_str(strip_code_fence(content)).context("label reply was not JSON")?;
    let category = value
        .get("category")
        .and_then(Value::as_str)
        .context("label reply has no category")?
        .to_string();
    if !categories.contains(&category) {
        return Err(anyhow!("label category {category} is not allowed"));
    }
    let confidence = value
        .get("confidence")
        .and_then(Value::as_f64)
        .unwrap_or(0.5);
    Ok((category, confidence.clamp(0.0, 1.0)))
}

impl Labeller {
    pub fn new(cfg: LabelConfig) -> Self {
        Self {
            cfg,
            http: reqwest::Client::new(),
        }
    }

    pub fn is_enabled(&self) -> bool {
        self.cfg.api_key.is_some()
    }

    pub fn model(&self) -> &str {
        &self.cfg.model
    }

    pub fn deadline(&self) -> Duration {
        self.cfg.deadline
    }

    pub async fn label_all(
        &self,
        storage: &Storage,
        categories: &[String],
        requests: Vec<LabelRequest>,
    ) -> LabelOutcome {
        let all_ids: Vec<String> = requests.iter().map(|r| r.observation_id.clone()).collect();
        if !self.is_enabled() || requests.is_empty() {
            return LabelOutcome {
                unlabelled: all_ids,
                ..LabelOutcome::default()
            };
        }
        let deadline = Instant::now() + self.cfg.deadline;
        let mut set = self.spawn_label_tasks(storage, categories, requests);
        let (labelled, deadline_hit) = collect_until(&mut set, deadline).await;
        set.abort_all();
        let done: Vec<&str> = labelled.iter().map(|l| l.observation_id.as_str()).collect();
        let unlabelled = all_ids
            .iter()
            .filter(|id| !done.contains(&id.as_str()))
            .cloned()
            .collect();
        LabelOutcome {
            labelled,
            unlabelled,
            deadline_hit,
        }
    }

    fn spawn_label_tasks(
        &self,
        storage: &Storage,
        categories: &[String],
        requests: Vec<LabelRequest>,
    ) -> JoinSet<Option<LabelResult>> {
        let permits = Arc::new(Semaphore::new(self.cfg.concurrency.max(1)));
        let categories: Arc<Vec<String>> = Arc::new(categories.to_vec());
        let mut set = JoinSet::new();
        for request in requests {
            let labeller = self.clone();
            let storage = storage.clone();
            let permits = Arc::clone(&permits);
            let categories = Arc::clone(&categories);
            set.spawn(async move {
                let _permit = permits.acquire_owned().await.ok()?;
                match labeller.label_one(&storage, &categories, &request).await {
                    Ok(result) => Some(result),
                    Err(err) => {
                        tracing::warn!(error = %err, id = %request.observation_id, "label failed");
                        None
                    }
                }
            });
        }
        set
    }

    async fn chat(&self, body: &Value) -> Result<String> {
        let reply: ChatResponse = self
            .http
            .post(format!(
                "{}/chat/completions",
                self.cfg.api_base.trim_end_matches('/')
            ))
            .bearer_auth(self.cfg.api_key.as_deref().unwrap_or_default())
            .timeout(self.cfg.request_timeout)
            .json(body)
            .send()
            .await?
            .error_for_status()?
            .json()
            .await?;
        reply
            .choices
            .into_iter()
            .next()
            .map(|c| c.message.content)
            .context("vision reply had no choices")
    }

    async fn image_data_uri(storage: &Storage, key: &str, content_type: &str) -> Result<String> {
        let bytes = storage.get_bytes(key).await?;
        Ok(format!(
            "data:{content_type};base64,{}",
            STANDARD.encode(bytes)
        ))
    }

    async fn label_one(
        &self,
        storage: &Storage,
        categories: &[String],
        request: &LabelRequest,
    ) -> Result<LabelResult> {
        let data_uri =
            Self::image_data_uri(storage, &request.crop_key, &request.content_type).await?;
        let body = build_request_body(&self.cfg.model, categories, &data_uri);
        let content = self.chat(&body).await?;
        let (category, confidence) = parse_label(&content, categories)?;
        Ok(LabelResult {
            observation_id: request.observation_id.clone(),
            category,
            confidence,
        })
    }

    /// Ask the model to answer one requirement question from a photo the owner took.
    pub async fn read_photo(
        &self,
        storage: &Storage,
        photo: &PhotoRef,
        question: &PhotoQuestion,
    ) -> Result<PhotoReading> {
        if !self.is_enabled() {
            return Err(anyhow!("photo reading is not configured"));
        }
        let data_uri = Self::image_data_uri(storage, &photo.key, &photo.content_type).await?;
        let body = build_photo_request_body(&self.cfg.model, question, &data_uri);
        parse_photo_reading(&self.chat(&body).await?, question)
    }
}

const PHOTO_SYSTEM_PROMPT: &str = "You check one accessibility requirement from a photo of a \
business interior, for an inspection screening. Answer only from what the photo shows. Reply \
with a JSON object {\"answer\": <value>, \"confidence\": <number between 0 and 1>} and \
nothing else. Use \"answer\": null when the photo does not show enough to answer.";

pub struct PhotoRef {
    pub key: String,
    pub content_type: String,
    pub sha256: String,
}

pub struct PhotoQuestion {
    pub prompt: String,
    pub value_type: String,
    pub unit: String,
    pub options: Vec<String>,
}

#[derive(Debug, PartialEq)]
pub struct PhotoReading {
    /// `None` when the model could not tell from the photo.
    pub answer: Option<Value>,
    pub confidence: f64,
}

fn answer_format(question: &PhotoQuestion) -> String {
    match question.value_type.as_str() {
        "boolean" => "The answer is true or false.".to_string(),
        "enum" => format!("The answer is one of: {}.", question.options.join(", ")),
        "number" | "integer" => format!("The answer is a number in {}.", question.unit),
        _ => "The answer is a short piece of text.".to_string(),
    }
}

pub fn build_photo_request_body(model: &str, question: &PhotoQuestion, data_uri: &str) -> Value {
    json!({
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": PHOTO_SYSTEM_PROMPT},
            {"role": "user", "content": [
                {"type": "text", "text": format!("{} {}", question.prompt, answer_format(question))},
                {"type": "image_url", "image_url": {"url": data_uri}},
            ]},
        ],
    })
}

fn answer_fits(answer: &Value, question: &PhotoQuestion) -> bool {
    match question.value_type.as_str() {
        "boolean" => answer.is_boolean(),
        "number" | "integer" => answer.as_f64().is_some_and(f64::is_finite),
        "enum" => answer
            .as_str()
            .is_some_and(|a| question.options.iter().any(|o| o == a)),
        _ => answer.is_string(),
    }
}

pub fn parse_photo_reading(content: &str, question: &PhotoQuestion) -> Result<PhotoReading> {
    let value: Value =
        serde_json::from_str(strip_code_fence(content)).context("photo reply was not JSON")?;
    let confidence = value
        .get("confidence")
        .and_then(Value::as_f64)
        .unwrap_or(0.5)
        .clamp(0.0, 1.0);
    let answer = value.get("answer").filter(|a| !a.is_null()).cloned();
    if let Some(answer) = &answer {
        if !answer_fits(answer, question) {
            return Err(anyhow!("photo answer {answer} does not fit the question"));
        }
    }
    Ok(PhotoReading { answer, confidence })
}

async fn collect_until(
    set: &mut JoinSet<Option<LabelResult>>,
    deadline: Instant,
) -> (Vec<LabelResult>, bool) {
    let mut labelled = Vec::new();
    loop {
        match tokio::time::timeout_at(deadline, set.join_next()).await {
            Err(_) => return (labelled, true),
            Ok(None) => return (labelled, false),
            Ok(Some(Ok(Some(result)))) => labelled.push(result),
            Ok(Some(_)) => {}
        }
    }
}

pub fn group_by_id(results: Vec<LabelResult>) -> HashMap<String, LabelResult> {
    results
        .into_iter()
        .map(|r| (r.observation_id.clone(), r))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn categories() -> Vec<String> {
        vec!["toilet".into(), "sink".into()]
    }

    #[test]
    fn parses_plain_and_fenced_json() {
        let plain =
            parse_label(r#"{"category":"toilet","confidence":0.9}"#, &categories()).unwrap();
        assert_eq!(plain, ("toilet".to_string(), 0.9));
        let fenced = parse_label("```json\n{\"category\":\"sink\"}\n```", &categories()).unwrap();
        assert_eq!(fenced.0, "sink");
    }

    #[test]
    fn rejects_unknown_category_and_prose() {
        assert!(parse_label(r#"{"category":"lamp"}"#, &categories()).is_err());
        assert!(parse_label("it is a toilet", &categories()).is_err());
    }

    #[test]
    fn request_body_lists_categories_and_image() {
        let body = build_request_body("m", &categories(), "data:image/jpeg;base64,AAAA");
        assert_eq!(body["model"], "m");
        let text = body["messages"][1]["content"][0]["text"].as_str().unwrap();
        assert!(text.contains("toilet, sink"));
    }
}

#[cfg(test)]
mod photo_tests {
    use super::*;

    fn question(value_type: &str) -> PhotoQuestion {
        PhotoQuestion {
            prompt: "Does the faucet have lever handles?".into(),
            value_type: value_type.into(),
            unit: "in".into(),
            options: vec!["lever".into(), "knob".into()],
        }
    }

    #[test]
    fn photo_answers_must_fit_the_question() {
        let yes = parse_photo_reading(r#"{"answer":true,"confidence":0.8}"#, &question("boolean"));
        assert_eq!(
            yes.unwrap(),
            PhotoReading {
                answer: Some(json!(true)),
                confidence: 0.8
            }
        );
        assert!(parse_photo_reading(r#"{"answer":"yes"}"#, &question("boolean")).is_err());
        assert!(parse_photo_reading(r#"{"answer":"knob"}"#, &question("enum")).is_ok());
        assert!(parse_photo_reading(r#"{"answer":"tap"}"#, &question("enum")).is_err());
        assert!(parse_photo_reading(r#"{"answer":34.5}"#, &question("number")).is_ok());
    }

    #[test]
    fn an_unclear_photo_gives_no_answer() {
        let reading =
            parse_photo_reading(r#"{"answer":null,"confidence":0.2}"#, &question("boolean"))
                .unwrap();
        assert_eq!(reading.answer, None);
    }

    #[test]
    fn the_prompt_says_what_shape_the_answer_takes() {
        let body = build_photo_request_body("m", &question("enum"), "data:image/jpeg;base64,AA");
        let text = body["messages"][1]["content"][0]["text"].as_str().unwrap();
        assert!(
            text.ends_with("The answer is one of: lever, knob."),
            "{text}"
        );
    }
}
