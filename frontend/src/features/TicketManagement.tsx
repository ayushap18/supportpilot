import { useEffect, useState } from "react";
import { MessageSquare, Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  NativeSelect,
  NativeSelectOption,
} from "@/components/ui/native-select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { Api, Note, Operations, Ticket, TicketInput } from "../types";
import { dateTime, words } from "./shared";

export function TicketManagement({
  ticket,
  members,
  busy,
  onUpdate,
}: {
  ticket: Ticket;
  members: Operations["members"];
  busy: boolean;
  onUpdate: (changes: Partial<Ticket>) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<TicketInput>(ticket);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  async function save(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      await onUpdate(form);
      setOpen(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  return (
    <div className="ticket-management">
      <div className="triage-fields">
        <label>
          Ticket status
          <NativeSelect
            aria-label="Ticket status"
            value={ticket.status}
            disabled={busy}
            onChange={(e) => {
              void onUpdate({
                status: e.target.value as Ticket["status"],
              }).catch(() => {});
            }}
          >
            {["open", "in_progress", "waiting", "resolved"].map((value) => (
              <NativeSelectOption key={value} value={value}>
                {words(value)}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </label>
        <label>
          Priority
          <NativeSelect
            aria-label="Priority"
            value={ticket.priority}
            disabled={busy}
            onChange={(e) => {
              void onUpdate({
                priority: e.target.value as Ticket["priority"],
              }).catch(() => {});
            }}
          >
            {["low", "normal", "high", "urgent"].map((value) => (
              <NativeSelectOption key={value} value={value}>
                {words(value)}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </label>
        <label>
          Assignee
          <NativeSelect
            aria-label="Assignee"
            value={ticket.assignee || ""}
            disabled={busy}
            onChange={(e) => {
              void onUpdate({ assignee: e.target.value || null }).catch(
                () => {},
              );
            }}
          >
            <NativeSelectOption value="">Unassigned</NativeSelectOption>
            {members.map((member) => (
              <NativeSelectOption
                key={member.reviewer_id}
                value={member.reviewer_id}
              >
                {member.reviewer_id}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </label>
      </div>
      <div className="ticket-management-foot">
        <span>
          Ticket revision {ticket.revision} ·{" "}
          {dateTime(ticket.updated_at || ticket.created_at)}
        </span>
        <Button
          variant="ghost"
          size="sm"
          disabled={busy}
          onClick={() => {
            setForm({
              subject: ticket.subject,
              description: ticket.description,
              product_version: ticket.product_version,
              account_id: ticket.account_id,
              log: ticket.log,
            });
            setError("");
            setOpen(true);
          }}
        >
          <Pencil size={13} />
          Edit context
        </Button>
      </div>
      <Dialog
        open={open}
        onOpenChange={(value) => {
          if (!saving) setOpen(value);
        }}
      >
        <DialogContent
          className="document-dialog"
          aria-label="Edit ticket context"
        >
          <DialogHeader>
            <DialogTitle>Edit ticket context</DialogTitle>
            <DialogDescription>
              Changes create a new ticket revision. Investigate again before
              reviewing a previous draft.
            </DialogDescription>
          </DialogHeader>
          <form className="stack-form" onSubmit={save}>
            {error && (
              <p className="error-banner" role="alert">
                {error}
              </p>
            )}
            <label>
              Ticket subject
              <Input
                required
                minLength={3}
                maxLength={200}
                value={form.subject}
                onChange={(e) => setForm({ ...form, subject: e.target.value })}
              />
            </label>
            <label>
              Ticket description
              <Textarea
                required
                minLength={10}
                maxLength={6000}
                rows={5}
                value={form.description}
                onChange={(e) =>
                  setForm({ ...form, description: e.target.value })
                }
              />
            </label>
            <div className="form-row">
              <label>
                Ticket API version
                <NativeSelect
                  value={form.product_version || ""}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      product_version: (e.target.value ||
                        null) as Ticket["product_version"],
                    })
                  }
                >
                  <NativeSelectOption value="">Unknown</NativeSelectOption>
                  <NativeSelectOption value="v1">v1</NativeSelectOption>
                  <NativeSelectOption value="v2">v2</NativeSelectOption>
                </NativeSelect>
              </label>
              <label>
                Ticket account ID
                <Input
                  value={form.account_id || ""}
                  maxLength={80}
                  onChange={(e) =>
                    setForm({ ...form, account_id: e.target.value || null })
                  }
                />
              </label>
            </div>
            <label>
              Ticket log
              <Textarea
                rows={3}
                maxLength={12000}
                value={form.log}
                onChange={(e) => setForm({ ...form, log: e.target.value })}
              />
            </label>
            <Button disabled={saving} type="submit">
              {saving ? "Saving…" : "Save context"}
            </Button>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export function TicketNotes({
  ticketId,
  api,
  onError,
  onChange,
}: {
  ticketId: string;
  api: Api;
  onError: (message: string) => void;
  onChange: () => Promise<void>;
}) {
  const [notes, setNotes] = useState<Note[]>([]),
    [body, setBody] = useState(""),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setNotes([]);
    setBody("");
    api<Note[]>(`/tickets/${ticketId}/notes`)
      .then((data) => {
        if (active) setNotes(data);
      })
      .catch((e) => {
        if (active) onError(e.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [ticketId]);
  async function add(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const note = await api<Note>(`/tickets/${ticketId}/notes`, {
        method: "POST",
        body: JSON.stringify({ body }),
      });
      setNotes((current) => [...current, note]);
      setBody("");
      await onChange();
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="ticket-notes">
      <h3>
        <MessageSquare size={16} />
        Internal notes <span>{notes.length}</span>
      </h3>
      {loading ? (
        <p className="muted">Loading notes…</p>
      ) : notes.length ? (
        <div className="note-list">
          {notes.map((note) => (
            <article key={note.id}>
              <div>
                <strong>{note.author_id}</strong>
                <time>{dateTime(note.created_at)}</time>
              </div>
              <p>{note.body}</p>
            </article>
          ))}
        </div>
      ) : (
        <p className="muted small">
          Record troubleshooting steps and handoff context for your team.
        </p>
      )}
      <form onSubmit={add}>
        <Textarea
          aria-label="Internal note"
          placeholder="Add context for the next reviewer…"
          value={body}
          maxLength={4000}
          required
          onChange={(e) => setBody(e.target.value)}
        />
        <Button
          variant="outline"
          size="sm"
          disabled={busy || !body.trim()}
          type="submit"
        >
          {busy ? "Saving…" : "Add note"}
        </Button>
      </form>
    </section>
  );
}
