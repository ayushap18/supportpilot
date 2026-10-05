import { useEffect, useRef, useState } from "react";
import {
  Archive,
  BookOpen,
  FileText,
  Plus,
  Search,
  Upload,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  NativeSelect,
  NativeSelectOption,
} from "@/components/ui/native-select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import type { Api, Evidence, KnowledgeDocument } from "../types";
import { dateTime, Empty, SectionHeading, StateBadge } from "./shared";
const blank = {
  title: "",
  body: "",
  product_version: "any" as "any" | "v1" | "v2",
  source_path: "",
};
export function KnowledgeView({
  api,
  admin,
  mode,
  onChange,
  onError,
}: {
  api: Api;
  admin: boolean;
  mode: string;
  onChange: () => Promise<void>;
  onError: (message: string) => void;
}) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [uploadError, setUploadError] = useState("");
  async function importFile(file: File | undefined) {
    if (!file) return;
    setUploadError("");
    try {
      if (!/\.(md|markdown|txt)$/i.test(file.name))
        throw new Error(
          "Choose a Markdown or plain-text file (.md, .markdown, .txt).",
        );
      if (file.size > 120000)
        throw new Error(
          "File is too large. Use up to 30,000 characters (120 KB).",
        );
      const body = new TextDecoder("utf-8", { fatal: true })
        .decode(await file.arrayBuffer())
        .trim();
      if (body.includes("\u0000") || body.length < 20 || body.length > 30000)
        throw new Error(
          "Use UTF-8 text containing 20–30,000 characters, without binary content.",
        );
      const filename = file.name.replace(/[\\/]/g, "_").slice(0, 190);
      const title = filename.replace(/\.[^.]+$/, "");
      setEditing(null);
      setForm({
        title: title.length >= 3 ? title : "Document " + title,
        body,
        product_version: "any",
        source_path: "upload/" + filename,
      });
      setModalError("");
      setOpen(true);
    } catch (error) {
      setUploadError((error as Error).message);
    } finally {
      if (fileInput.current) fileInput.current.value = "";
    }
  }
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]),
    [loading, setLoading] = useState(true),
    [query, setQuery] = useState(""),
    [version, setVersion] = useState("any"),
    [results, setResults] = useState<Evidence[] | null>(null),
    [editing, setEditing] = useState<KnowledgeDocument | null>(null),
    [open, setOpen] = useState(false),
    [form, setForm] = useState(blank),
    [busy, setBusy] = useState(""),
    [modalError, setModalError] = useState("");
  async function load() {
    const data = await api<{ items: KnowledgeDocument[] }>(
      "/knowledge/documents",
    );
    setDocuments(data.items);
  }
  useEffect(() => {
    let active = true;
    api<{ items: KnowledgeDocument[] }>("/knowledge/documents")
      .then((data) => {
        if (active) setDocuments(data.items);
      })
      .catch((e) => onError(e.message))
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);
  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy("save");
    setModalError("");
    try {
      await api("/knowledge/documents" + (editing ? "/" + editing.id : ""), {
        method: editing ? "PATCH" : "POST",
        body: JSON.stringify({
          ...form,
          ...(editing ? { expected_revision: editing.revision } : {}),
        }),
      });
      await load();
      await onChange();
      setResults(null);
      setOpen(false);
    } catch (e) {
      setModalError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  async function archive(document: KnowledgeDocument) {
    setBusy(document.id);
    try {
      await api(
        `/knowledge/documents/${document.id}/${document.archived ? "restore" : "archive"}`,
        {
          method: "POST",
          body: JSON.stringify({ expected_revision: document.revision }),
        },
      );
      await load();
      await onChange();
      setResults(null);
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  async function search(event: React.FormEvent) {
    event.preventDefault();
    setBusy("search");
    try {
      const data = await api<{ evidence: Evidence[] }>("/knowledge/search", {
        method: "POST",
        body: JSON.stringify({
          query,
          product_version: version === "any" ? null : version,
        }),
      });
      setResults(data.evidence);
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  return (
    <>
      <Card>
        <CardContent>
          <SectionHeading
            title="Knowledge library"
            detail="Versioned documentation used to ground every investigation"
            action={
              admin ? (
                <div className="heading-actions">
                  <input
                    ref={fileInput}
                    type="file"
                    accept=".md,.markdown,.txt"
                    aria-label="Upload knowledge file"
                    hidden
                    onChange={(event) =>
                      void importFile(event.target.files?.[0])
                    }
                  />
                  <Button
                    variant="outline"
                    onClick={() => fileInput.current?.click()}
                    disabled={!!busy}
                  >
                    <Upload size={16} />
                    Upload file
                  </Button>
                  <Button
                    onClick={() => {
                      setEditing(null);
                      setForm(blank);
                      setModalError("");
                      setOpen(true);
                    }}
                  >
                    <Plus size={16} />
                    Add document
                  </Button>
                </div>
              ) : (
                <StateBadge value="agent" />
              )
            }
          />
          {uploadError && (
            <p className="error-banner" role="alert">
              {uploadError}
            </p>
          )}
          <form className="knowledge-search" onSubmit={search}>
            <div className="search-field">
              <Search size={16} />
              <Input
                aria-label="Knowledge search"
                placeholder="Test a question against your documentation…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                required
                minLength={2}
              />
            </div>
            <NativeSelect
              aria-label="Knowledge version"
              value={version}
              onChange={(e) => setVersion(e.target.value)}
            >
              <NativeSelectOption value="any">All versions</NativeSelectOption>
              <NativeSelectOption value="v1">v1</NativeSelectOption>
              <NativeSelectOption value="v2">v2</NativeSelectOption>
            </NativeSelect>
            <Button variant="outline" disabled={!!busy} type="submit">
              Search knowledge
            </Button>
          </form>
          <p className="muted small">
            {mode === "fixture"
              ? "Fixture retrieval uses lexical matching. Custom documents can be tested here; demo drafts follow the bundled examples."
              : "Live retrieval uses semantic embeddings."}{" "}
            Archived documents are excluded.{" "}
            {admin ? "" : "Your agent role can read and search documents."}
          </p>
        </CardContent>
      </Card>
      {results !== null && (
        <Card>
          <CardContent>
            <SectionHeading
              title="Search results"
              detail={`${results.length} retrieved evidence passages`}
              action={
                <Button variant="ghost" onClick={() => setResults(null)}>
                  Clear results
                </Button>
              }
            />
            {results.length ? (
              results.map((item) => (
                <div className="evidence-card" key={item.id}>
                  <FileText size={17} />
                  <div>
                    <strong>{item.title}</strong>
                    <p>{item.excerpt}</p>
                    <small>
                      {item.source_path} ·{" "}
                      {item.product_version || "Any version"}
                    </small>
                  </div>
                </div>
              ))
            ) : (
              <Empty title="No matching evidence">
                Try another question or add documentation that covers this
                topic.
              </Empty>
            )}
          </CardContent>
        </Card>
      )}
      <div className="document-grid">
        {loading ? (
          <p className="muted">Loading documents…</p>
        ) : documents.length ? (
          documents.map((document) => (
            <Card
              key={document.id}
              className={
                document.archived ? "document-card archived" : "document-card"
              }
            >
              <CardContent>
                <div className="document-heading">
                  <span className="document-icon">
                    <BookOpen size={20} />
                  </span>
                  <StateBadge
                    value={
                      document.archived
                        ? "archived"
                        : document.origin === "seed"
                          ? "demo source"
                          : "workspace"
                    }
                  />
                </div>
                <h3>{document.title}</h3>
                <p className="document-preview">{document.body}</p>
                <div className="document-meta">
                  <span>
                    {document.product_version === "any"
                      ? "All versions"
                      : document.product_version}
                  </span>
                  <span>{document.chunk_count} chunks</span>
                  <span>Revision {document.revision}</span>
                </div>
                <small className="muted">
                  {document.updated_at
                    ? dateTime(document.updated_at)
                    : "Bundled reference"}
                </small>
                <div className="document-actions">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setEditing(document);
                      setForm({
                        title: document.title,
                        body: document.body,
                        product_version: document.product_version,
                        source_path: document.source_path || "",
                      });
                      setModalError("");
                      setOpen(true);
                    }}
                  >
                    {admin &&
                    document.origin === "workspace" &&
                    !document.archived
                      ? "Edit document"
                      : "View document"}
                  </Button>
                  {admin && document.origin === "workspace" && (
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={!!busy}
                      onClick={() => archive(document)}
                    >
                      <Archive size={14} />
                      {document.archived ? "Restore" : "Archive"}
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          ))
        ) : (
          <Empty title="Add your first document">
            Start with product setup, troubleshooting, or support policies.
          </Empty>
        )}
      </div>
      <Dialog
        open={open}
        onOpenChange={(value) => {
          if (!busy) setOpen(value);
        }}
      >
        <DialogContent
          className="document-dialog"
          aria-label={editing ? "Document details" : "Add document"}
        >
          <DialogHeader>
            <DialogTitle>
              {editing ? "Document details" : "Add document"}
            </DialogTitle>
            <DialogDescription>
              Plain text or Markdown. Changes are indexed before they become
              searchable.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={save} className="stack-form">
            {modalError && (
              <p className="error-banner" role="alert">
                {modalError}
              </p>
            )}
            <label>
              Document title
              <Input
                value={form.title}
                required
                minLength={3}
                maxLength={200}
                readOnly={
                  !admin || editing?.origin === "seed" || editing?.archived
                }
                onChange={(e) => setForm({ ...form, title: e.target.value })}
              />
            </label>
            <div className="form-row">
              <label>
                Document version
                <NativeSelect
                  aria-label="Document version"
                  value={form.product_version}
                  disabled={
                    !admin || editing?.origin === "seed" || editing?.archived
                  }
                  onChange={(e) =>
                    setForm({
                      ...form,
                      product_version: e.target
                        .value as typeof form.product_version,
                    })
                  }
                >
                  <NativeSelectOption value="any">
                    Any version
                  </NativeSelectOption>
                  <NativeSelectOption value="v1">v1</NativeSelectOption>
                  <NativeSelectOption value="v2">v2</NativeSelectOption>
                </NativeSelect>
              </label>
              <label>
                Source path
                <Input
                  value={form.source_path}
                  maxLength={200}
                  readOnly={
                    !admin || editing?.origin === "seed" || editing?.archived
                  }
                  onChange={(e) =>
                    setForm({ ...form, source_path: e.target.value })
                  }
                  placeholder="docs/troubleshooting.md"
                />
              </label>
            </div>
            <label>
              Document content
              <Textarea
                value={form.body}
                required
                minLength={20}
                maxLength={30000}
                rows={12}
                readOnly={
                  !admin || editing?.origin === "seed" || editing?.archived
                }
                onChange={(e) => setForm({ ...form, body: e.target.value })}
              />
            </label>
            {admin && editing?.origin !== "seed" && !editing?.archived && (
              <Button disabled={!!busy} type="submit">
                {busy === "save" ? "Indexing document…" : "Save document"}
              </Button>
            )}
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
