/**
 * Remove sintaxe Markdown do texto para envio ao SpeechSynthesis.
 * Não é completo — cobre os elementos mais comuns gerados pelo Haiku.
 */
export function stripMarkdown(md: string): string {
  return md
    // Headers
    .replace(/^#{1,6}\s+/gm, "")
    // Bold/italic
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/\*(.+?)\*/g, "$1")
    .replace(/__(.+?)__/g, "$1")
    .replace(/_(.+?)_/g, "$1")
    // Inline code
    .replace(/`([^`]+)`/g, "$1")
    // Code fences
    .replace(/```[\s\S]*?```/g, "")
    // Links — mantém só o texto
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    // Bullets
    .replace(/^[-*+]\s+/gm, "")
    // Numbered lists
    .replace(/^\d+\.\s+/gm, "")
    // Blockquotes — Haiku às vezes gera "> texto"; sem isso o TTS lê "maior que"
    .replace(/^>\s+/gm, "")
    // Tabela: remove pipes e separadores
    .replace(/^\|.+\|$/gm, (line) => line.replace(/\|/g, " ").trim())
    .replace(/^[\s|:-]+$/gm, "")
    // Múltiplas quebras
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}
