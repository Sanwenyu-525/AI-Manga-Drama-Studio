// Native OS directory picker (Tauri desktop shell only).
// 浏览器安全沙箱不允许网页从原生选择框拿到绝对路径，因此「浏览目录」按钮只在
// Tauri 壳内走原生对话框；调用方（设置页）在浏览器环境回落内置 DirectoryBrowserModal。
// 检测沿用 shell 组件的 "__TAURI_INTERNALS__" 惯例，但做成函数：测试可动态注入。

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
