// Native OS directory picker (Tauri desktop shell only).
// 浏览器安全沙箱不允许网页从原生选择框拿到绝对路径，因此「浏览目录」按钮只在
// Tauri 壳内走原生对话框；调用方（设置页）在浏览器环境回落内置 DirectoryBrowserModal。
// 检测沿用 shell 组件的 "__TAURI_INTERNALS__" 惯例，但做成函数：测试可动态注入。
//
// 方案 B（真实本地导入）：Tauri 壳内读取用户选中的 .txt/.md 文本经 Rust 命令
// read_text_file / list_text_dir 完成（只读、不落库），浏览器环境回落 FileReader /
// webkitdirectory。红线：导入永远经用户在 UI 操作，Agent 不直接碰文件系统。

export function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

/** Open the native folder picker; resolves the picked absolute path or null on cancel. */
export async function pickDirectory(title: string, initialDir?: string): Promise<string | null> {
  // 动态 import：浏览器环境（测试/纯 Web）永不加载插件模块。
  const { open } = await import("@tauri-apps/plugin-dialog");
  const picked = await open({
    directory: true,
    multiple: false,
    title,
    defaultPath: initialDir && initialDir.trim() ? initialDir.trim() : undefined,
  });
  return typeof picked === "string" ? picked : null;
}

/** Open the native file picker for one text file; resolves absolute path or null on cancel. */
export async function pickTextFile(title: string, initialDir?: string): Promise<string | null> {
  const { open } = await import("@tauri-apps/plugin-dialog");
  const picked = await open({
    multiple: false,
    title,
    filters: [
      { name: "文本文件", extensions: ["txt", "md", "markdown", "text"] },
      { name: "所有文件", extensions: ["*"] },
    ],
    defaultPath: initialDir && initialDir.trim() ? initialDir.trim() : undefined,
  });
  return typeof picked === "string" ? picked : null;
}

/** 目录下文本稿条目（相对路径展示 + 绝对路径读取）。 */
export interface TextDirEntry {
  path: string;
  name: string;
  abs_path: string;
}

/** 递归列出目录下的 .txt/.md/.markdown/.text 文件（经 Rust 命令，只读）。 */
export async function listTextDir(dir: string): Promise<TextDirEntry[]> {
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<TextDirEntry[]>("list_text_dir", { dir });
}

/** 读取一个本地文本文件的内容（经 Rust 命令，只读，5 MB 上限）。 */
export async function readTextFile(path: string): Promise<string> {
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<string>("read_text_file", { path });
}
