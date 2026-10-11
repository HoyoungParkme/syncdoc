//! 설정 파일 — 데이터 자리의 `settings.toml` (SYNC-INFRA-001 5.2·9.3).
//! 키 이름은 파이썬 판 환경 변수와 같다(사용자 결정 2026-10-07). 설정 「이 PC」·「백업」 카드가 값만 바꾼다(L16).

use std::fs;
use std::path::Path;

use syncdoc_core::errors::Problem;
use syncdoc_server::local::SettingsChange;

pub const FILE: &str = "settings.toml";

const KEYS: [&str; 8] = [
    "LOCAL_LOGIN",
    "LOCAL_NAME",
    "LLM_API_URL",
    "LLM_API_KEY",
    "LLM_MODEL",
    "PUBLIC_BASE_URL",
    "BACKUP_DIR",
    "BACKUP_PASSWORD",
];

/// 첫 실행 때 쓰는 파일 — 키 여덟과 기본값, 키마다 설명
const DEFAULT: &str = "\
# 싱크독_로컬 설정 — 고친 뒤 다시 켜면 반영된다
# 키 이름은 싱크독_깃허브(파이썬 판)의 환경 변수와 같다 (INFRA 5.2)

# 로컬 사용자 아이디 — 커밋 작성자({아이디}@syncdoc.local). 50자까지
LOCAL_LOGIN = \"local\"

# 이력·설정에 보이는 이름 — 비면 LOCAL_LOGIN
LOCAL_NAME = \"\"

# 질문 탭의 모델 — 사내 OpenAI 호환 주소와 키. 둘 다 있어야 질문 탭이 생긴다
LLM_API_URL = \"\"
LLM_API_KEY = \"\"
LLM_MODEL = \"gpt-4o\"

# 같은 망에 열기 — 예 http://192.168.0.10:8010. 비면 이 PC(127.0.0.1)에서만
# 열면 그 망의 누구나 로그인 없이 쓴다. 화면에서는 바꾸지 않는다 (INFRA 9.4)
PUBLIC_BASE_URL = \"\"

# 하루 한 번 백업할 폴더(절대 경로) — 비면 백업하지 않는다. 최근 14개만 남긴다 (INFRA 9.6)
BACKUP_DIR = \"\"

# 백업 암호 — 비면 암호 없이(.tar). 잃으면 백업을 못 푼다 — 이 PC 밖에도 적어 둔다
BACKUP_PASSWORD = \"\"
";

/// 읽은 설정 — 파생값까지
#[derive(Clone, Debug)]
pub struct Settings {
    pub local_login: String,
    pub local_name: String,
    /// 파일의 `LOCAL_NAME` 그대로 — 설정 화면이 보인다
    pub local_name_raw: String,
    pub llm_api_url: String,
    pub llm_api_key: String,
    pub llm_model: String,
    pub llm_enabled: bool,
    /// 같은 망 열기 — 끝 `/`를 뗀 것, 비면 이 PC만 (INFRA 9.4)
    pub public_base_url: String,
    /// 백업 폴더 — 비면 백업하지 않는다 (INFRA 9.6)
    pub backup_dir: String,
    /// 백업 암호 — 비면 암호 없이
    pub backup_password: String,
}

/// SYNC-MS-012#settings.load
pub fn load(data_dir: &Path) -> Result<Settings, Problem> {
    let path = data_dir.join(FILE);
    if !path.exists() {
        write_private(&path, DEFAULT)?;
    }
    let text = fs::read_to_string(&path)?;
    let table: toml::Table = text
        .parse()
        .map_err(|e: toml::de::Error| Problem::Internal {
            log: format!("{}을 못 읽는다 — {e}", path.display()),
        })?;
    for k in table.keys() {
        if !KEYS.contains(&k.as_str()) {
            tracing::warn!("{FILE}: 모르는 키 {k} — 쓰지 않는다");
        }
    }
    let get = |key: &str, default: &str| -> Result<String, Problem> {
        match table.get(key) {
            None => Ok(default.to_string()),
            Some(toml::Value::String(s)) => Ok(s.clone()),
            Some(_) => Err(Problem::Internal {
                log: format!("{}: {key}는 글자여야 한다", path.display()),
            }),
        }
    };
    let local_login = get("LOCAL_LOGIN", "local")?;
    let name = get("LOCAL_NAME", "")?;
    let llm_api_url = get("LLM_API_URL", "")?.trim().to_string();
    let llm_api_key = get("LLM_API_KEY", "")?;
    let llm_model = get("LLM_MODEL", "gpt-4o")?;
    let public_base_url = get("PUBLIC_BASE_URL", "")?
        .trim()
        .trim_end_matches('/')
        .to_string();
    let backup_dir = get("BACKUP_DIR", "")?.trim().to_string();
    let backup_password = get("BACKUP_PASSWORD", "")?;
    let local_name = match name.trim() {
        "" => local_login.clone(),
        n => n.to_string(),
    };
    if local_login.is_empty() || local_login.chars().count() > 50 {
        return Err(Problem::Internal {
            log: format!("{}: LOCAL_LOGIN은 1~50자여야 한다", path.display()),
        });
    }
    if local_name.chars().count() > 100 {
        return Err(Problem::Internal {
            log: format!("{}: LOCAL_NAME은 100자까지다", path.display()),
        });
    }
    if !public_base_url.is_empty() && host_of(&public_base_url).is_none() {
        return Err(Problem::Internal {
            log: format!(
                "{}: PUBLIC_BASE_URL은 http(s)://이름[:포트]여야 한다",
                path.display()
            ),
        });
    }
    if !backup_dir.is_empty() && !Path::new(&backup_dir).is_absolute() {
        return Err(Problem::Internal {
            log: format!("{}: BACKUP_DIR은 절대 경로여야 한다", path.display()),
        });
    }
    let llm_enabled = !llm_api_key.is_empty() && !llm_api_url.is_empty();
    Ok(Settings {
        local_login,
        local_name,
        local_name_raw: name,
        llm_api_url,
        llm_api_key,
        llm_model,
        llm_enabled,
        public_base_url,
        backup_dir,
        backup_password,
    })
}

/// `http(s)://` 뒤의 `이름[:포트]` — 경로·질의는 무시한다. 없으면 `None`
pub fn host_of(url: &str) -> Option<String> {
    let rest = url
        .strip_prefix("http://")
        .or_else(|| url.strip_prefix("https://"))?;
    let netloc = rest.split(['/', '?', '#']).next().unwrap_or("");
    (!netloc.is_empty() && !netloc.starts_with(':')).then(|| netloc.to_lowercase())
}

/// SYNC-MS-012#settings.save
///
/// 값만 바꾼다 — 주석·다른 키·차례는 그대로, 없던 키는 끝에. 옆 임시 파일에 쓰고 이름을 바꾼다
pub fn save(data_dir: &Path, change: &SettingsChange) -> Result<(), Problem> {
    let path = data_dir.join(FILE);
    if !path.exists() {
        write_private(&path, DEFAULT)?;
    }
    let text = fs::read_to_string(&path)?;
    let mut doc: toml_edit::DocumentMut =
        text.parse()
            .map_err(|e: toml_edit::TomlError| Problem::Internal {
                log: format!("{}을 못 읽는다 — {e}", path.display()),
            })?;
    for (key, value) in [
        ("LOCAL_NAME", &change.name),
        ("LLM_API_URL", &change.llm_api_url),
        ("LLM_API_KEY", &change.llm_api_key),
        ("LLM_MODEL", &change.llm_model),
        ("BACKUP_DIR", &change.backup_dir),
        ("BACKUP_PASSWORD", &change.backup_password),
    ] {
        let Some(v) = value else { continue };
        match doc.get_mut(key).and_then(|item| item.as_value_mut()) {
            // 값만 — 키 앞뒤의 주석·꾸밈은 그대로
            Some(old) => {
                let decor = old.decor().clone();
                *old = toml_edit::Value::from(v.as_str());
                *old.decor_mut() = decor;
            }
            None => {
                doc[key] = toml_edit::value(v.as_str());
            }
        }
    }
    let tmp = path.with_extension("toml.tmp");
    write_private(&tmp, &doc.to_string())?;
    fs::rename(&tmp, &path)?;
    Ok(())
}

/// 사용자만 읽는 파일로 쓴다 — 모델 키가 든다
fn write_private(path: &Path, text: &str) -> Result<(), Problem> {
    fs::write(path, text)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(path, fs::Permissions::from_mode(0o600))?;
    }
    Ok(())
}
