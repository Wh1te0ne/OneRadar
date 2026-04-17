use std::collections::HashMap;
use std::env;
use std::fs;
use std::path::{Path, PathBuf};

use aes_gcm::aead::{Aead, KeyInit};
use aes_gcm::{Aes256Gcm, Nonce};
use base64::engine::general_purpose::STANDARD;
use base64::Engine;
use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};
use tempfile::NamedTempFile;
#[cfg(target_os = "windows")]
use windows_sys::Win32::Foundation::LocalFree;
#[cfg(target_os = "windows")]
use windows_sys::Win32::Security::Cryptography::{CryptUnprotectData, CRYPT_INTEGER_BLOB};

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
struct BrowserCookieSource {
    browser_id: String,
    browser_name: String,
    profile_name: String,
    cookie_count: usize,
    has_full_set: bool,
    cookie_header: String,
    sessdata: Option<String>,
    bili_jct: Option<String>,
    buvid3: Option<String>,
    sessdata_preview: Option<String>,
    bili_jct_preview: Option<String>,
    buvid3_preview: Option<String>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct BrowserCookieReadResponse {
    selected: Option<BrowserCookieSource>,
    sources: Vec<BrowserCookieSource>,
    message: String,
}

#[derive(Debug)]
struct BrowserCandidate {
    browser_id: &'static str,
    browser_name: &'static str,
    user_data_dir: PathBuf,
}

#[derive(Debug, Deserialize)]
struct ChromiumLocalState {
    os_crypt: Option<ChromiumOsCrypt>,
}

#[derive(Debug, Deserialize)]
struct ChromiumOsCrypt {
    encrypted_key: String,
}

#[tauri::command]
fn read_local_bilibili_cookie() -> Result<BrowserCookieReadResponse, String> {
    read_local_bilibili_cookie_impl()
}

#[cfg(not(target_os = "windows"))]
fn read_local_bilibili_cookie_impl() -> Result<BrowserCookieReadResponse, String> {
    Err("当前仅支持 Windows 桌面版读取本机 Chromium Cookie。".into())
}

#[cfg(target_os = "windows")]
fn read_local_bilibili_cookie_impl() -> Result<BrowserCookieReadResponse, String> {
    let candidates = browser_candidates()?;
    if candidates.is_empty() {
        return Err("未发现可扫描的 Chromium 浏览器数据目录。".into());
    }

    let mut sources: Vec<BrowserCookieSource> = Vec::new();
    for candidate in candidates {
        let Ok(master_key) = load_master_key(&candidate.user_data_dir) else {
            continue;
        };
        for profile_dir in profile_directories(&candidate.user_data_dir) {
            let Ok(Some(source)) = read_profile_cookie_source(&candidate, &profile_dir, &master_key) else {
                continue;
            };
            sources.push(source);
        }
    }

    if sources.is_empty() {
        return Ok(BrowserCookieReadResponse {
            selected: None,
            sources,
            message: "没有在本机 Chromium 浏览器里找到 Bilibili 的关键 Cookie。请先在浏览器中登录 Bilibili。".into(),
        });
    }

    let selected = sources
        .iter()
        .find(|source| source.has_full_set)
        .cloned()
        .or_else(|| sources.first().cloned());

    let message = if let Some(source) = &selected {
        format!(
            "已从 {} / {} 读取到 {} 个 Bilibili Cookie 字段。",
            source.browser_name, source.profile_name, source.cookie_count
        )
    } else {
        "已读取本机浏览器 Cookie。".into()
    };

    Ok(BrowserCookieReadResponse {
        selected,
        sources,
        message,
    })
}

#[cfg(target_os = "windows")]
fn browser_candidates() -> Result<Vec<BrowserCandidate>, String> {
    let local_app_data = PathBuf::from(env::var("LOCALAPPDATA").map_err(|_| "无法读取 LOCALAPPDATA。")?);
    let definitions = vec![
        ("chrome", "Google Chrome", local_app_data.join("Google").join("Chrome").join("User Data")),
        ("edge", "Microsoft Edge", local_app_data.join("Microsoft").join("Edge").join("User Data")),
        ("brave", "Brave", local_app_data.join("BraveSoftware").join("Brave-Browser").join("User Data")),
    ];

    Ok(definitions
        .into_iter()
        .filter(|(_, _, dir)| dir.exists())
        .map(|(browser_id, browser_name, user_data_dir)| BrowserCandidate {
            browser_id,
            browser_name,
            user_data_dir,
        })
        .collect())
}

#[cfg(target_os = "windows")]
fn profile_directories(user_data_dir: &Path) -> Vec<PathBuf> {
    let mut profiles = Vec::new();
    if let Ok(entries) = fs::read_dir(user_data_dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            if !path.is_dir() {
                continue;
            }
            let Some(name) = path.file_name().and_then(|value| value.to_str()) else {
                continue;
            };
            if name == "Default" || name.starts_with("Profile ") {
                profiles.push(path);
            }
        }
    }
    profiles.sort();
    profiles
}

#[cfg(target_os = "windows")]
fn read_profile_cookie_source(
    candidate: &BrowserCandidate,
    profile_dir: &Path,
    master_key: &[u8],
) -> Result<Option<BrowserCookieSource>, String> {
    let Some(cookie_path) = cookie_db_path(profile_dir) else {
        return Ok(None);
    };
    let temp_copy = copy_cookie_db(&cookie_path)?;
    let connection = Connection::open(temp_copy.path()).map_err(|error| error.to_string())?;
    let mut statement = connection
        .prepare(
            "SELECT name, value, encrypted_value FROM cookies WHERE host_key LIKE ?1 AND name IN ('SESSDATA', 'bili_jct', 'buvid3')",
        )
        .map_err(|error| error.to_string())?;

    let mut rows = statement
        .query(params!["%bilibili.com%"])
        .map_err(|error| error.to_string())?;
    let mut cookies = HashMap::<String, String>::new();
    while let Some(row) = rows.next().map_err(|error| error.to_string())? {
        let name: String = row.get(0).map_err(|error| error.to_string())?;
        let value: String = row.get(1).unwrap_or_default();
        let encrypted_value: Vec<u8> = row.get(2).unwrap_or_default();
        let decrypted = if !value.trim().is_empty() {
            value.trim().to_string()
        } else {
            decrypt_cookie_value(&encrypted_value, master_key)?
        };
        if !decrypted.is_empty() {
            cookies.insert(name, decrypted);
        }
    }

    if cookies.is_empty() {
        return Ok(None);
    }

    let profile_name = profile_dir
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("Default")
        .to_string();
    let sessdata = cookies.get("SESSDATA").cloned();
    let bili_jct = cookies.get("bili_jct").cloned();
    let buvid3 = cookies.get("buvid3").cloned();
    let cookie_header = [
        sessdata.as_ref().map(|value| format!("SESSDATA={value}")),
        bili_jct.as_ref().map(|value| format!("bili_jct={value}")),
        buvid3.as_ref().map(|value| format!("buvid3={value}")),
    ]
    .into_iter()
    .flatten()
    .collect::<Vec<_>>()
    .join("; ");

    Ok(Some(BrowserCookieSource {
        browser_id: candidate.browser_id.to_string(),
        browser_name: candidate.browser_name.to_string(),
        profile_name,
        cookie_count: cookies.len(),
        has_full_set: sessdata.is_some() && bili_jct.is_some() && buvid3.is_some(),
        cookie_header,
        sessdata_preview: mask_value(sessdata.as_deref()),
        bili_jct_preview: mask_value(bili_jct.as_deref()),
        buvid3_preview: mask_value(buvid3.as_deref()),
        sessdata,
        bili_jct,
        buvid3,
    }))
}

#[cfg(target_os = "windows")]
fn cookie_db_path(profile_dir: &Path) -> Option<PathBuf> {
    let network_path = profile_dir.join("Network").join("Cookies");
    if network_path.exists() {
        return Some(network_path);
    }
    let legacy_path = profile_dir.join("Cookies");
    if legacy_path.exists() {
        return Some(legacy_path);
    }
    None
}

#[cfg(target_os = "windows")]
fn copy_cookie_db(source: &Path) -> Result<NamedTempFile, String> {
    let temp_file = NamedTempFile::new().map_err(|error| error.to_string())?;
    fs::copy(source, temp_file.path()).map_err(|error| error.to_string())?;
    Ok(temp_file)
}

#[cfg(target_os = "windows")]
fn load_master_key(user_data_dir: &Path) -> Result<Vec<u8>, String> {
    let local_state_path = user_data_dir.join("Local State");
    let raw = fs::read_to_string(local_state_path).map_err(|error| error.to_string())?;
    let local_state: ChromiumLocalState = serde_json::from_str(&raw).map_err(|error| error.to_string())?;
    let encrypted_key = local_state
        .os_crypt
        .map(|os_crypt| os_crypt.encrypted_key)
        .ok_or_else(|| "Local State 中缺少 os_crypt.encrypted_key。".to_string())?;
    let mut encrypted_key = STANDARD.decode(encrypted_key).map_err(|error| error.to_string())?;
    if encrypted_key.starts_with(b"DPAPI") {
        encrypted_key.drain(0..5);
    }
    crypt_unprotect_bytes(&encrypted_key)
}

#[cfg(target_os = "windows")]
fn decrypt_cookie_value(encrypted_value: &[u8], master_key: &[u8]) -> Result<String, String> {
    if encrypted_value.is_empty() {
        return Ok(String::new());
    }
    if encrypted_value.starts_with(b"v10") || encrypted_value.starts_with(b"v11") {
        if encrypted_value.len() < 31 {
            return Err("cookie 密文长度异常。".into());
        }
        let cipher = Aes256Gcm::new_from_slice(master_key).map_err(|error| error.to_string())?;
        let nonce = Nonce::from_slice(&encrypted_value[3..15]);
        let ciphertext = &encrypted_value[15..];
        let decrypted = cipher
            .decrypt(nonce, ciphertext)
            .map_err(|_| "AES-GCM 解密失败。".to_string())?;
        return Ok(String::from_utf8_lossy(&decrypted).trim().to_string());
    }
    let decrypted = crypt_unprotect_bytes(encrypted_value)?;
    Ok(String::from_utf8_lossy(&decrypted).trim().to_string())
}

#[cfg(target_os = "windows")]
fn mask_value(value: Option<&str>) -> Option<String> {
    let value = value?.trim();
    if value.is_empty() {
        return None;
    }
    if value.len() <= 8 {
        return Some("*".repeat(value.len()));
    }
    Some(format!("{}...{}", &value[..4], &value[value.len() - 4..]))
}

#[cfg(target_os = "windows")]
fn crypt_unprotect_bytes(value: &[u8]) -> Result<Vec<u8>, String> {
    unsafe {
        let mut input = CRYPT_INTEGER_BLOB {
            cbData: value.len() as u32,
            pbData: value.as_ptr() as *mut u8,
        };
        let mut output = CRYPT_INTEGER_BLOB {
            cbData: 0,
            pbData: std::ptr::null_mut(),
        };
        let ok = CryptUnprotectData(
            &mut input,
            std::ptr::null_mut(),
            std::ptr::null_mut(),
            std::ptr::null_mut(),
            std::ptr::null_mut(),
            0,
            &mut output,
        );
        if ok == 0 {
            return Err("Windows DPAPI 解密失败。".into());
        }
        let bytes = std::slice::from_raw_parts(output.pbData, output.cbData as usize).to_vec();
        LocalFree(output.pbData as _);
        Ok(bytes)
    }
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![read_local_bilibili_cookie])
        .run(tauri::generate_context!())
        .expect("failed to run OneRadar desktop shell");
}
