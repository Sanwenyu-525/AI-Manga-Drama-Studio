// 本地文本文件读取（方案 B：Tauri 真实本地导入，mvp-spec DOC/B-*）。
//
// 只读、不写、不落库：webview 经 invoke 读取用户选中的 .txt/.md 文本，
// 内容仍先进 textarea 由用户审阅后保存（与浏览器版语义一致，红线：导入
// 永远经用户在 UI 操作，Agent 不直接碰文件系统）。
//
// 权限面最小化：不引入 tauri-plugin-fs（避免打开任意路径读写权限），
// 仅两个窄命令，且由本应用前端独占调用。

use std::path::Path;

const TEXT_EXTENSIONS: &[&str] = &["txt", "md", "markdown", "text"];
const MAX_TEXT_BYTES: u64 = 5 * 1024 * 1024; // 5 MB 上限（LLM 分析预算内）

#[derive(serde::Serialize)]
pub struct TextDirEntry {
    /// 相对路径（相对所选目录，用于 UI 展示，与浏览器版 webkitRelativePath 一致）。
    pub path: String,
    /// 文件名（去目录）。
    pub name: String,
    /// 绝对路径（供 read_text_file 读取）。
    pub abs_path: String,
}

/// 读取一个 UTF-8 文本文件的内容（大小受限）。
#[tauri::command]
pub fn read_text_file(path: String) -> Result<String, String> {
    let p = Path::new(&path);
    if !p.is_file() {
        return Err(format!("Not a file: {path}"));
    }
    let meta = std::fs::metadata(p).map_err(|e| e.to_string())?;
    if meta.len() > MAX_TEXT_BYTES {
        return Err(format!("File too large (max {} bytes)", MAX_TEXT_BYTES));
    }
    std::fs::read_to_string(p).map_err(|e| e.to_string())
}

/// 递归列出目录下的 .txt/.md/.markdown/.text 文件（相对路径，深度受限）。
#[tauri::command]
pub fn list_text_dir(dir: String) -> Result<Vec<TextDirEntry>, String> {
    let root = Path::new(&dir);
    if !root.is_dir() {
        return Err(format!("Not a directory: {dir}"));
    }
    let mut out = Vec::new();
    collect_text_files(root, "", &mut out, 0)?;
    out.sort_by(|a, b| a.path.cmp(&b.path));
    Ok(out)
}

fn collect_text_files(
    dir: &Path,
    prefix: &str,
    out: &mut Vec<TextDirEntry>,
    depth: usize,
) -> Result<(), String> {
    if depth > 8 {
        return Ok(()); // 防深嵌套目录失控
    }
    for entry in std::fs::read_dir(dir).map_err(|e| e.to_string())? {
        let entry = entry.map_err(|e| e.to_string())?;
        let path = entry.path();
        let name = entry.file_name().to_string_lossy().into_owned();
        let rel = if prefix.is_empty() {
            name.clone()
        } else {
            format!("{prefix}/{name}")
        };
        if path.is_dir() {
            collect_text_files(&path, &rel, out, depth + 1)?;
        } else if path.is_file() {
            let ext = path
                .extension()
                .map(|e| e.to_string_lossy().to_lowercase())
                .unwrap_or_default();
            if TEXT_EXTENSIONS.contains(&ext.as_str()) {
                out.push(TextDirEntry {
                    abs_path: path.to_string_lossy().into_owned(),
                    path: rel,
                    name,
                });
            }
        }
    }
    Ok(())
}
