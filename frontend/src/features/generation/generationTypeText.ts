// TASK-012: zh labels for generation kinds in the queue dock (raw ids stay for unknown types).
export function generationTypeText(type: string | null | undefined): string {
  return (
    (
      {
        image: "图片",
        render: "整集渲染",
        audio: "配音",
      } as Record<string, string>
    )[type ?? "image"] ??
    type ??
    "图片"
  );
}
