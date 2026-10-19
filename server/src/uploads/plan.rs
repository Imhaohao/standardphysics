use crate::error::{ApiError, ApiResult};

pub const MIN_PART_SIZE: i64 = 5 * 1024 * 1024;
pub const DEFAULT_PART_SIZE: i64 = 8 * 1024 * 1024;
pub const MAX_PARTS: i64 = 10_000;
pub const MAX_OBJECT_SIZE: i64 = 5 * 1024 * 1024 * 1024 * 1024;
pub const MAX_PRESIGN_BATCH: usize = 200;

#[derive(Debug, PartialEq, Eq)]
pub struct PartPlan {
    pub part_size: i64,
    pub part_count: i32,
}

fn ceil_div(value: i64, divisor: i64) -> i64 {
    (value + divisor - 1) / divisor
}

pub fn plan_parts(size_bytes: i64, requested: Option<i64>) -> ApiResult<PartPlan> {
    if size_bytes <= 0 || size_bytes > MAX_OBJECT_SIZE {
        return Err(ApiError::bad_request("size_bytes is out of range"));
    }
    let requested = requested.unwrap_or(DEFAULT_PART_SIZE);
    if requested < MIN_PART_SIZE {
        return Err(ApiError::bad_request("part_size must be at least 5 MiB"));
    }
    let part_size = requested.max(ceil_div(size_bytes, MAX_PARTS));
    let part_count = ceil_div(size_bytes, part_size) as i32;
    Ok(PartPlan {
        part_size,
        part_count,
    })
}

pub fn valid_kind(kind: &str) -> bool {
    !kind.is_empty()
        && kind.len() <= 32
        && kind
            .chars()
            .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_' || c == '-')
}

pub fn safe_filename(raw: &str) -> String {
    let cleaned: String = raw
        .chars()
        .map(|c| {
            if c.is_ascii_alphanumeric() || c == '.' || c == '_' || c == '-' {
                c
            } else {
                '_'
            }
        })
        .take(120)
        .collect();
    let trimmed = cleaned.trim_matches('.').to_string();
    if trimmed.is_empty() {
        "file".to_string()
    } else {
        trimmed
    }
}

pub fn valid_sha256(value: &str) -> bool {
    value.len() == 64 && value.chars().all(|c| c.is_ascii_hexdigit())
}

pub fn validate_part_numbers(numbers: &[i32], part_count: i32) -> ApiResult<()> {
    if numbers.is_empty() || numbers.len() > MAX_PRESIGN_BATCH {
        return Err(ApiError::bad_request(
            "part_numbers must list 1 to 200 parts",
        ));
    }
    if numbers.iter().any(|n| *n < 1 || *n > part_count) {
        return Err(ApiError::bad_request("part number is outside this upload"));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn small_file_is_one_part() {
        let plan = plan_parts(1000, None).unwrap();
        assert_eq!(plan.part_count, 1);
    }

    #[test]
    fn huge_file_grows_part_size_to_stay_under_part_limit() {
        let plan = plan_parts(200 * 1024 * 1024 * 1024, Some(MIN_PART_SIZE)).unwrap();
        assert!(i64::from(plan.part_count) <= MAX_PARTS);
    }

    #[test]
    fn rejects_tiny_part_size_and_empty_files() {
        assert!(plan_parts(10, Some(1024)).is_err());
        assert!(plan_parts(0, None).is_err());
    }

    #[test]
    fn filenames_are_sanitised() {
        assert_eq!(safe_filename("../../etc/passwd"), "_.._etc_passwd");
        assert_eq!(safe_filename("..."), "file");
        assert_eq!(safe_filename("room 1.json"), "room_1.json");
    }
}
