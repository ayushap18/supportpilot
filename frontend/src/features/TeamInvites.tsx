import { useEffect, useState } from "react";
import { UserPlus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  NativeSelect,
  NativeSelectOption,
} from "@/components/ui/native-select";
import type { Api } from "../types";
import { dateTime, SectionHeading } from "./shared";

type Invite = {
  id: string;
  login: string;
  role: string;
  invited_by: string;
  created_at: string;
};

export function TeamInvites({
  api,
  admin,
  onError,
}: {
  api: Api;
  admin: boolean;
  onError: (message: string) => void;
}) {
  const [invites, setInvites] = useState<Invite[]>([]);
  const [login, setLogin] = useState("");
  const [role, setRole] = useState("agent");
  const [busy, setBusy] = useState("");
  const [sent, setSent] = useState("");

  async function load() {
    setInvites((await api<{ items: Invite[] }>("/auth/invites")).items);
  }
  useEffect(() => {
    load().catch((e) => onError(e.message));
  }, []);

  async function invite(event: React.FormEvent) {
    event.preventDefault();
    setBusy("invite");
    setSent("");
    try {
      const created = await api<Invite>("/auth/invites", {
        method: "POST",
        body: JSON.stringify({ login: login.trim().replace(/^@/, ""), role }),
      });
      setSent(created.login);
      setLogin("");
      await load();
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  async function revoke(id: string) {
    setBusy(id);
    try {
      await api("/auth/invites/" + id, { method: "DELETE" });
      await load();
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  return (
    <Card>
      <CardContent>
        <SectionHeading
          title="Team"
          detail="Invite teammates by GitHub username. They accept after verifying with GitHub and receive their own token."
        />
        {admin ? (
          <form className="invite-form" onSubmit={invite}>
            <Input
              aria-label="GitHub username"
              placeholder="GitHub username"
              required
              pattern="@?[A-Za-z0-9][A-Za-z0-9\-]{0,38}"
              value={login}
              onChange={(e) => setLogin(e.target.value)}
            />
            <NativeSelect
              aria-label="Invite role"
              value={role}
              onChange={(e) => setRole(e.target.value)}
            >
              <NativeSelectOption value="agent">Member</NativeSelectOption>
              <NativeSelectOption value="admin">Admin</NativeSelectOption>
            </NativeSelect>
            <Button className="primary" disabled={!!busy}>
              <UserPlus size={15} />
              Invite
            </Button>
          </form>
        ) : (
          <p className="muted small">
            Only workspace admins can invite teammates.
          </p>
        )}
        {sent && (
          <p className="muted small" role="status">
            Invitation created for @{sent}. Ask them to sign in at this
            SupportPilot address with GitHub.
          </p>
        )}
        {invites.length ? (
          <div
            className="repo-list invite-list"
            aria-label="Pending invitations"
          >
            {invites.map((item) => (
              <div className="repo-row" key={item.id}>
                <UserPlus size={15} />
                <div>
                  <strong>@{item.login}</strong>
                  <span>
                    {item.role === "admin" ? "Admin" : "Member"} · invited by{" "}
                    {item.invited_by} · {dateTime(item.created_at)}
                  </span>
                </div>
                {admin && (
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label={"Revoke invitation for " + item.login}
                    disabled={!!busy}
                    onClick={() => revoke(item.id)}
                  >
                    <X size={14} />
                  </Button>
                )}
              </div>
            ))}
          </div>
        ) : (
          <p className="muted small">No pending invitations.</p>
        )}
      </CardContent>
    </Card>
  );
}
