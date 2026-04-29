export function displayFolderName(name?: string | null, isInbox?: boolean) {
  const value = (name ?? "").trim();
  if (isInbox || value === "收件箱" || value.toLowerCase() === "inbox") return "稍后阅读";
  return value || "未分类";
}
