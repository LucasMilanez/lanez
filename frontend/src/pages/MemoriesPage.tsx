import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { formatDistanceToNow } from "date-fns";
import { ptBR, enUS } from "date-fns/locale";
import { Brain, Plus, Pencil, Trash2, Check, X, Tag } from "lucide-react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { ErrorState } from "@/components/ErrorState";
import { useI18n, interpolate } from "@/i18n/I18nContext";
import { api } from "@/lib/api";

interface Memory {
  id: string;
  content: string;
  tags: string[];
  created_at: string;
}

const fetchMemories = () => api.get<Memory[]>("/memories");

const createMemory = (data: { content: string; tags: string[] }) =>
  api.post<Memory>("/memories", data);

const updateMemory = (id: string, data: { content?: string; tags?: string[] }) =>
  api.patch<Memory>(`/memories/${id}`, data);

const deleteMemory = (id: string) => api.del<void>(`/memories/${id}`);

function TagsInput({
  value,
  onChange,
}: {
  value: string[];
  onChange: (tags: string[]) => void;
}) {
  const [input, setInput] = useState("");
  const { t } = useI18n();

  function addTag() {
    const tag = input.trim();
    if (tag && !value.includes(tag)) {
      onChange([...value, tag]);
    }
    setInput("");
  }

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <Input
          placeholder={t.memoriesPage.addTag}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              addTag();
            }
          }}
          className="h-8 text-sm"
        />
        <Button type="button" variant="outline" size="sm" onClick={addTag}>
          <Tag className="h-3.5 w-3.5" />
        </Button>
      </div>
      {value.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {value.map((tag) => (
            <Badge
              key={tag}
              variant="secondary"
              className="gap-1 cursor-pointer hover:bg-destructive/10 hover:text-destructive transition-colors"
              onClick={() => onChange(value.filter((t2) => t2 !== tag))}
            >
              {tag}
              <X className="h-3 w-3" />
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}

function MemoryRow({ memory, onSaved }: { memory: Memory; onSaved: () => void }) {
  const [editing, setEditing] = useState(false);
  const [content, setContent] = useState(memory.content);
  const [tags, setTags] = useState(memory.tags);
  const qc = useQueryClient();
  const { t, locale } = useI18n();

  const update = useMutation({
    mutationFn: () => updateMemory(memory.id, { content, tags }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["memories"] });
      setEditing(false);
      toast.success(t.memoriesPage.updated);
      onSaved();
    },
    onError: () => toast.error(t.memoriesPage.errorUpdate),
  });

  const remove = useMutation({
    mutationFn: () => deleteMemory(memory.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["memories"] });
      toast.success(t.memoriesPage.deleted);
    },
    onError: () => toast.error(t.memoriesPage.errorDelete),
  });

  function handleDelete() {
    if (window.confirm(t.memoriesPage.confirmDelete)) {
      remove.mutate();
    }
  }

  function handleCancel() {
    setContent(memory.content);
    setTags(memory.tags);
    setEditing(false);
  }

  if (editing) {
    return (
      <div className="rounded-lg border border-border bg-card p-4 space-y-3">
        <Textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          rows={3}
          className="text-sm resize-none"
          autoFocus
        />
        <TagsInput value={tags} onChange={setTags} />
        <div className="flex gap-2 justify-end">
          <Button variant="ghost" size="sm" onClick={handleCancel}>
            <X className="h-4 w-4 mr-1.5" />
            {t.common.cancel}
          </Button>
          <Button
            size="sm"
            onClick={() => update.mutate()}
            disabled={!content.trim() || update.isPending}
          >
            <Check className="h-4 w-4 mr-1.5" />
            {t.common.save}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="group rounded-lg border border-border bg-card px-4 py-3 flex gap-3">
      <div className="flex-1 min-w-0 space-y-2">
        <p className="text-sm text-foreground whitespace-pre-wrap">{memory.content}</p>
        <div className="flex flex-wrap items-center gap-2">
          {memory.tags.map((tag) => (
            <Badge key={tag} variant="secondary" className="text-xs">
              {tag}
            </Badge>
          ))}
          <span className="text-[11px] text-muted-foreground">
            {formatDistanceToNow(new Date(memory.created_at), {
              addSuffix: true,
              locale: locale === "pt" ? ptBR : enUS,
            })}
          </span>
        </div>
      </div>
      <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={() => setEditing(true)}
          aria-label={t.common.edit}
        >
          <Pencil className="h-3.5 w-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 hover:text-destructive hover:bg-destructive/10"
          onClick={handleDelete}
          disabled={remove.isPending}
          aria-label={t.common.delete}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );
}

function NewMemoryForm({ onDone }: { onDone: () => void }) {
  const [content, setContent] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const qc = useQueryClient();
  const { t } = useI18n();

  const create = useMutation({
    mutationFn: () => createMemory({ content, tags }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["memories"] });
      setContent("");
      setTags([]);
      toast.success(t.memoriesPage.saved);
      onDone();
    },
    onError: () => toast.error(t.memoriesPage.errorSave),
  });

  return (
    <div className="rounded-lg border border-brand/40 bg-card p-4 space-y-3">
      <Textarea
        placeholder={t.memoriesPage.writeMemory}
        value={content}
        onChange={(e) => setContent(e.target.value)}
        rows={3}
        className="text-sm resize-none"
        autoFocus
      />
      <TagsInput value={tags} onChange={setTags} />
      <div className="flex gap-2 justify-end">
        <Button variant="ghost" size="sm" onClick={onDone}>
          <X className="h-4 w-4 mr-1.5" />
          {t.common.cancel}
        </Button>
        <Button
          size="sm"
          onClick={() => create.mutate()}
          disabled={!content.trim() || create.isPending}
        >
          <Check className="h-4 w-4 mr-1.5" />
          {t.common.save}
        </Button>
      </div>
    </div>
  );
}

export function MemoriesPage() {
  const [adding, setAdding] = useState(false);
  const { t } = useI18n();
  const { data, isLoading, error, refetch } = useQuery<Memory[]>({
    queryKey: ["memories"],
    queryFn: fetchMemories,
  });

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-20 w-full rounded-lg" />
        ))}
      </div>
    );
  }

  if (error) {
    return <ErrorState onRetry={() => void refetch()} />;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Brain className="h-4 w-4" />
          <span className="text-sm">{interpolate(t.memoriesPage.memoriesCount, { count: data?.length ?? 0 })}</span>
        </div>
        {!adding && (
          <Button size="sm" onClick={() => setAdding(true)}>
            <Plus className="h-4 w-4 mr-1.5" />
            {t.memoriesPage.newMemory}
          </Button>
        )}
      </div>

      {adding && <NewMemoryForm onDone={() => setAdding(false)} />}

      {data && data.length === 0 && !adding && (
        <Card className="shadow-soft">
          <CardContent className="flex flex-col items-center justify-center py-12 gap-3 text-center">
            <Brain className="h-8 w-8 text-muted-foreground/40" />
            <p className="text-sm text-muted-foreground">
              {t.memoriesPage.noMemories}
            </p>
            <Button size="sm" variant="outline" onClick={() => setAdding(true)}>
              <Plus className="h-4 w-4 mr-1.5" />
              {t.memoriesPage.createFirst}
            </Button>
          </CardContent>
        </Card>
      )}

      {data && data.length > 0 && (
        <Card className="shadow-soft">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-sm font-semibold tracking-tight">
              <Brain className="h-4 w-4 text-muted-foreground" />
              {t.memoriesPage.allMemories}
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0 space-y-2">
            {data.map((memory) => (
              <MemoryRow key={memory.id} memory={memory} onSaved={() => {}} />
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
