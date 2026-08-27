// 记住最近打开的工作台项目，供 /assets /workflows /settings 等页面返回工作台用。
// 浏览器/WebView 本地存储；尽力而为，失败则静默降级。

const KEY = "studio-last-project";

export function rememberProject(projectId: string): void {
  try {
    localStorage.setItem(KEY, projectId);
  } catch {
    /* storage unavailable — ignore */
  }
}

export function lastProjectId(): string | null {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}