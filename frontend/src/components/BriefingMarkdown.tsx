import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface BriefingMarkdownProps {
  content: string;
}

export function BriefingMarkdown({ content }: BriefingMarkdownProps) {
  return (
    <div className="prose prose-slate dark:prose-invert max-w-none">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  );
}
