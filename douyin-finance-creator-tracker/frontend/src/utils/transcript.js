/**
 * Extract the body of the "内容综述" section from the AI-generated Markdown.
 * The section ends at the following heading of the same or a higher level.
 */
export function extractContentOverview(markdown) {
  if (!markdown) return "";

  const lines = String(markdown).replace(/\r\n?/g, "\n").split("\n");
  const headingIndex = lines.findIndex((line) =>
    /^#{1,6}\s+(?:💡\s*)?内容综述\s*$/.test(line.trim())
  );
  if (headingIndex === -1) return "";

  const content = [];
  for (const line of lines.slice(headingIndex + 1)) {
    if (/^#{1,6}\s+/.test(line.trim())) break;
    content.push(line.trim());
  }

  return content
    .join(" ")
    .replace(/\s+/g, " ")
    .replace(/\*\*(.*?)\*\*/g, "$1")
    .trim();
}
