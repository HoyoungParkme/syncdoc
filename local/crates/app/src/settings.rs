//! 설정 파일 — 데이터 자리의 `settings.toml` (SYNC-INFRA-001 5.2·9.3).
//! 키 이름은 파이썬 판 환경 변수와 같다(사용자 결정 2026-10-07). 「이 PC」 화면(L16) 전까지는 이 파일을 고친다.

use std::fs;
use std::path::Path;

use syncdoc_core::errors::Problem;

pub const FILE: &str = "settings.toml";

const KEYS: [&str; 5] = [
    "LOCAL_LOGIN",
    "LOCAL_NAME",
    "LLM_API_URL",
    "LLM_API_KEY",
    "LLM_MODEL",
];

/// 첫 실행 때 쓰는 파일 — 키 다섯과 기본값, 키마다 설명
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
";

/// 읽은 설정 — 파생값까지
#[derive(Clone, Debug)]
pub struct Settings {
    pub local_login: String,
    pub local_name: String,
    pub llm_api_url: String,
    pub llm_api_key: String,
    pub llm_model: String,
    pub llm_enabled: bool,
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
    let llm_enabled = !llm_api_key.is_empty() && !llm_api_url.is_empty();
    Ok(Settings {
        local_login,
        local_name,
        llm_api_url,
        llm_api_key,
        llm_model,
        llm_enabled,
    })
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
