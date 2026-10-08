"""`supportpilot` command line: status, tickets, investigations, agent runs, and autopilot.

Presentation uses only the standard library: ANSI color on terminals (respects NO_COLOR),
aligned tables, and `--json` for scripts. Runner commands reuse `cli_bridge`.
"""

import argparse
import json
import os
import shutil
import sys
import textwrap
import time
from datetime import UTC, datetime

import httpx

from supportpilot import cli_bridge as bridge

FIX_TASK = (
    "Fix the issue described in the linked ticket if it is caused by code in this repository. "
    "Make the smallest correct change, add or update a test when practical, and run the "
    "relevant tests. If the ticket is not caused by this repository's code, change nothing "
    "and explain why."
)


class Style:
    def __init__(self, stream=sys.stdout):
        self.on = stream.isatty() and not os.environ.get("NO_COLOR")

    def __getattr__(self, name):
        codes = {"bold": 1, "dim": 2, "red": 31, "green": 32, "yellow": 33, "blue": 34,
                 "violet": 35, "cyan": 36}  # fmt: skip
        code = codes[name]
        return lambda text: f"\033[{code}m{text}\033[0m" if self.on else str(text)


S = Style()
TONE = {
    "open": S.cyan, "in_progress": S.blue, "waiting": S.yellow, "resolved": S.green,
    "queued": S.blue, "running": S.cyan, "completed": S.green, "failed": S.red,
    "cancelled": S.dim, "pending": S.yellow, "approved": S.green, "rejected": S.red,
    "stale": S.dim, "none": S.dim, "urgent": S.red, "high": S.yellow, "normal": S.dim,
    "low": S.dim, "escalate": S.yellow, "needs_information": S.violet,
}  # fmt: skip


def tone(value):
    return TONE.get(str(value), str)(str(value).replace("_", " "))


def visible(text):
    """Length without ANSI codes, for column alignment."""
    out, skip = 0, False
    for ch in str(text):
        if ch == "\033":
            skip = True
        elif skip and ch == "m":
            skip = False
        elif not skip:
            out += 1
    return out


def table(headers, rows):
    """Aligned columns; the last column is truncated to the terminal width."""
    if not rows:
        print(S.dim("  Nothing here."))
        return
    widths = [max(visible(r[i]) for r in [headers, *rows]) for i in range(len(headers) - 1)]
    budget = shutil.get_terminal_size((120, 20)).columns - sum(widths) - 2 * len(widths) - 2
    print("  " + "  ".join(S.dim(h.ljust(w)) for h, w in zip(headers, widths)) + "  " + S.dim(headers[-1]))
    for row in rows:
        cells = [str(c) + " " * (w - visible(c)) for c, w in zip(row, widths)]
        last = str(row[-1])
        if len(last) > max(budget, 20):
            last = last[: max(budget, 20) - 1] + "…"
        print("  " + "  ".join(cells) + "  " + last)


def short(ticket_id):
    return "TKT-" + ticket_id[:6].upper()


def age(stamp):
    if not stamp:
        return "–"
    seconds = (datetime.now(UTC) - datetime.fromisoformat(str(stamp))).total_seconds()
    for limit, unit, size in ((90, "s", 1), (5400, "m", 60), (172800, "h", 3600)):
        if seconds < limit:
            return f"{int(seconds // size)}{unit}"
    return f"{int(seconds // 86400)}d"


def log(symbol, text, color=str):
    print(S.dim(datetime.now().strftime("%H:%M:%S")), color(symbol), text, flush=True)


class Api:
    def __init__(self, repository="."):
        self.base, token = bridge.connection(repository)
        self.client = httpx.Client(
            base_url=self.base, headers={"Authorization": "Bearer " + token}, timeout=240
        )

    def __call__(self, method, path, **kwargs):
        try:
            response = self.client.request(method, "/api" + path, **kwargs)
        except httpx.HTTPError as exc:
            raise SystemExit(f"Cannot reach SupportPilot at {self.base} ({type(exc).__name__}).")
        if response.status_code in (401, 403) and path == "/session":
            raise SystemExit("Workspace token rejected. Run `supportpilot login` again.")
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail")
            except ValueError:
                detail = None
            raise ApiError(response.status_code, detail or response.reason_phrase)
        return response.json()


class ApiError(Exception):
    def __init__(self, status, detail):
        super().__init__(f"{detail} (HTTP {status})")
        self.status = status


def find_ticket(api, ref):
    ref = ref.lower().removeprefix("tkt-")
    items = api("GET", "/queue", params={"page_size": 100})["items"]
    matches = [t for t in items if t["id"].lower().startswith(ref)]
    if len(matches) != 1:
        raise SystemExit(f"{'No' if not matches else 'Several'} tickets match {ref!r}.")
    return matches[0]


# ---- commands --------------------------------------------------------------------------


def cmd_status(args):
    api = Api(args.repository)
    me = api("GET", "/session")
    ops = api("GET", "/operations")
    mission = api("GET", "/mission")
    runners = [r for r in api("GET", "/agents/runners")["items"] if r["online"]]
    if args.json:
        return print(json.dumps({"session": me, "pipeline": mission["pipeline"],
                                 "runners": runners, "model": ops["model"]}, indent=2))  # fmt: skip
    p = mission["pipeline"]
    rows = [
        ("Server", S.green("●") + " " + api.base),
        ("Workspace", f"{me.get('label') or me['workspace_id']} · {me['role']} as {me['reviewer_id']}"),
        ("Mode", f"{ops['mode']} · {ops['model']}"),
        ("Runners", (S.green(f"{len(runners)} online") + " · " + ", ".join(
            f"{r['runner_id']} ({', '.join(r['providers'])})" for r in runners))
            if runners else S.yellow("none online") + S.dim(" · start one with `supportpilot watch`")),
        ("Pipeline", " · ".join([
            f"{p['queued']} queued", S.cyan(f"{p['running']} running"),
            S.yellow(f"{p['awaiting_review']} need review"), S.green(f"{p['accepted']} accepted"),
            S.red(f"{p['failed']} failed")])),
        ("Needs you", f"{len(mission['work_queue'])} items" + S.dim("  · supportpilot tickets")),
    ]  # fmt: skip
    print()
    print(" ", S.bold("SupportPilot"))
    for label, value in rows:
        print("  " + S.dim(label.ljust(11)) + value)
    print()


def cmd_tickets(args):
    api = Api(args.repository)
    params = {"page_size": 100, "status": args.status}
    if args.review:
        params["review"] = "pending"
    items = api("GET", "/queue", params=params)["items"]
    if args.json:
        return print(json.dumps(items, indent=2))
    print()
    table(
        ["TICKET", "STATUS", "PRIORITY", "REVIEW", "UPDATED", "SUBJECT"],
        [
            (S.bold(short(t["id"])), tone(t["status"]), tone(t["priority"]),
             tone(t["review_status"]), age(t["updated_at"] or t["created_at"]), t["subject"])
            for t in items
        ],
    )  # fmt: skip
    print()


def cmd_investigate(args):
    api = Api(args.repository)
    ticket = find_ticket(api, args.ticket)
    print()
    print(" ", S.bold(short(ticket["id"])), ticket["subject"])
    print(" ", S.dim("Investigating… (live mode can take 20–60 s)"), flush=True)
    started = time.monotonic()
    inv = api(
        "POST",
        f"/tickets/{ticket['id']}/investigations",
        headers={"Idempotency-Key": f"cli-{ticket['id']}-{int(time.time())}"},
    )
    if args.json:
        return print(json.dumps(inv, indent=2))
    print_investigation(inv, time.monotonic() - started)


def print_investigation(inv, seconds):
    print()
    if inv["state"] == "failed":
        print(" ", S.red("✗ Investigation failed:"), inv.get("error") or "unknown error")
        return
    draft = inv["draft"]
    print(" ", tone(draft["outcome"]).upper(), S.dim(f"· {seconds:.1f}s"))
    for step in inv["trace"]:
        print("   ", S.dim(f"{step['stage']:<9}"), step["summary"][:110])
    print()
    width = min(100, shutil.get_terminal_size((100, 20)).columns - 4)
    for paragraph in draft["response"].split("\n"):
        print(textwrap.fill(paragraph, width, initial_indent="  ", subsequent_indent="  "))
    cited = {e["id"]: e for e in inv["evidence"]}
    if draft["evidence_ids"]:
        print()
        print(" ", S.dim("Sources"))
        for n, eid in enumerate(draft["evidence_ids"], 1):
            source = cited.get(eid, {})
            print("   ", S.green(str(n)), source.get("title") or eid)
    print()
    print(" ", S.dim("Approve or reject it in the app's Review queue, or let `supportpilot auto` decide."))
    print()


def cmd_runs(args):
    api = Api(args.repository)
    items = api("GET", "/agents/runs")["items"][: args.limit]
    if args.json:
        return print(json.dumps(items, indent=2))
    print()
    table(
        ["RUN", "AGENT", "STATUS", "REPOSITORY", "AGE", "TASK"],
        [
            (S.bold(r["id"][:8]), r["provider"], tone(r["status"]),
             r.get("repository_full_name") or "–", age(r["created_at"]), r["task"].splitlines()[0])
            for r in items
        ],
    )  # fmt: skip
    print()


def cmd_auto(args):
    """Autopilot: investigate, approve, fix, and open draft PRs without a person in the loop."""
    api = Api(args.repository)
    me = api("GET", "/session")
    remote = bridge.origin_repository(args.repository)
    if me["role"] != "admin":
        raise SystemExit("Autopilot needs an admin workspace token.")
    print()
    print(" ", S.bold("SupportPilot autopilot"), S.dim("· Ctrl+C to stop"))
    print("  " + S.dim("workspace ") + (me.get("label") or me["workspace_id"]))
    print("  " + S.dim("repository") + " " + (remote or S.yellow("no GitHub origin; fixes disabled")))
    steps = ["investigate new tickets"]
    if not args.no_approve:
        steps.append("approve resolved drafts with sources")
    if remote and not args.no_fix:
        steps.append(f"fix escalations with {args.agent} → draft PR")
    print("  " + S.dim("does      ") + " · ".join(steps))
    print()
    try:
        while True:
            autopilot_cycle(api, args, remote)
            if args.once:
                return 0
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print()
        log("■", "Autopilot stopped.", S.dim)
        return 0


def autopilot_cycle(api, args, remote):
    tickets = api("GET", "/queue", params={"page_size": 100})["items"]

    # 1. Investigate tickets that have never been investigated (one idempotency key per ticket,
    # so a restart can never investigate the same ticket twice).
    fresh = [t for t in tickets if not t["investigation_state"] and t["status"] != "resolved"]
    for ticket in fresh[: args.max_per_cycle]:
        log("●", f"Investigating {S.bold(short(ticket['id']))} {ticket['subject'][:70]}", S.cyan)
        try:
            inv = api(
                "POST",
                f"/tickets/{ticket['id']}/investigations",
                headers={"Idempotency-Key": "autopilot-" + ticket["id"]},
            )
        except ApiError as exc:
            log("✗", f"Investigation failed: {exc}", S.red)
            continue
        outcome = (inv.get("draft") or {}).get("outcome", inv["state"])
        log("·", f"{short(ticket['id'])} → {tone(outcome)}", S.dim)
    if fresh:
        tickets = api("GET", "/queue", params={"page_size": 100})["items"]

    # 2. Approve drafts that resolve the ticket and cite sources; mark the ticket resolved.
    if not args.no_approve:
        for ticket in [t for t in tickets if t["review_status"] == "pending"]:
            inv = api("GET", f"/investigations/{ticket['latest_investigation_id']}")
            draft = inv.get("draft") or {}
            if draft.get("outcome") != "resolved" or not draft.get("evidence_ids"):
                continue
            try:
                api(
                    "POST",
                    f"/investigations/{inv['id']}/reviews",
                    json={
                        "draft_revision": inv["draft_revision"],
                        "decision": "approve",
                        "note": f"Auto-approved by supportpilot autopilot: resolved with "
                        f"{len(draft['evidence_ids'])} cited sources.",
                    },
                )
                api(
                    "PATCH",
                    f"/tickets/{ticket['id']}",
                    json={"expected_revision": ticket["revision"], "status": "resolved"},
                )
                log("✓", f"Approved and resolved {S.bold(short(ticket['id']))}", S.green)
            except ApiError as exc:
                log("✗", f"Could not approve {short(ticket['id'])}: {exc}", S.red)

    if not remote or args.no_fix:
        return

    # 3. One fix run per escalated ticket.
    runs = api("GET", "/agents/runs")["items"]
    has_run = {r.get("ticket_id") for r in runs}
    escalated = [
        t for t in tickets
        if t["latest_outcome"] == "escalate" and t["status"] != "resolved" and t["id"] not in has_run
    ]  # fmt: skip
    for ticket in escalated[: args.max_per_cycle]:
        run = api(
            "POST",
            "/agents/runs",
            json={
                "provider": args.agent,
                "task": FIX_TASK,
                "ticket_id": ticket["id"],
                "repository_full_name": remote,
                "allow_edits": True,
            },
        )
        log("→", f"Queued {args.agent} fix run {run['id'][:8]} for {short(ticket['id'])}", S.violet)

    # 4. Execute queued runs here, with edits and push enabled on this machine.
    if any(r["status"] == "queued" for r in api("GET", "/agents/runs")["items"]):
        bridge.watch(
            args.repository, allow_edits=True, push=True, timeout=args.timeout, once=True
        )

    # 5. Open a draft PR for every completed run whose branch was pushed.
    for run in api("GET", "/agents/runs")["items"]:
        artifacts = run.get("artifacts") or []
        pushed = any(
            a.get("kind") == "branch" and str(a.get("label", "")).endswith("(pushed)")
            for a in artifacts
        )
        has_pr = any(a.get("kind") == "pull_request" for a in artifacts)
        if run["status"] == "completed" and pushed and not has_pr:
            try:
                opened = api("POST", f"/github/agent-runs/{run['id']}/pull-request")
                url = next(a["url"] for a in opened["artifacts"] if a["kind"] == "pull_request")
                log("↗", f"Opened draft PR {url}", S.green)
            except ApiError as exc:
                log("✗", f"Could not open PR for run {run['id'][:8]}: {exc}", S.red)


# ---- entry point -----------------------------------------------------------------------


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="supportpilot",
        description="SupportPilot from the terminal: status, tickets, investigations, agent "
        "runs, and autopilot. Run inside a repository checkout; `login` once first.",
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="command")

    def add(name, help_text, func):
        p = sub.add_parser(name, help=help_text, description=help_text)
        p.add_argument("--repository", default=".", help="checkout to use (default: here)")
        p.set_defaults(func=func)
        return p

    for name, help_text, func in (
        ("status", "workspace, mode, runners, and pipeline at a glance", cmd_status),
        ("runs", "recent agent runs", cmd_runs),
    ):
        add(name, help_text, func).add_argument("--json", action="store_true")
    sub.choices["runs"].add_argument("--limit", type=int, default=15)

    p = add("tickets", "tickets with status, review state, and age", cmd_tickets)
    p.add_argument("--status", default="all",
                   choices=["all", "open", "in_progress", "waiting", "resolved"])  # fmt: skip
    p.add_argument("--review", action="store_true", help="only drafts awaiting review")
    p.add_argument("--json", action="store_true")

    p = add("investigate", "investigate a ticket and print the cited draft", cmd_investigate)
    p.add_argument("ticket", help="ticket ID or prefix, e.g. TKT-BE421F")
    p.add_argument("--json", action="store_true")

    p = add("auto", "autopilot: investigate, approve, fix, and open draft PRs", cmd_auto)
    p.add_argument("--agent", default="codex", choices=["codex", "antigravity"],
                   help="agent for fix runs (default: codex)")  # fmt: skip
    p.add_argument("--interval", type=int, default=20, help="seconds between cycles")
    p.add_argument("--max-per-cycle", type=int, default=3, help="new tickets/fix runs per cycle")
    p.add_argument("--timeout", type=int, default=900, help="agent run time limit in seconds")
    p.add_argument("--no-approve", action="store_true", help="leave drafts for a person")
    p.add_argument("--no-fix", action="store_true", help="do not queue agent fix runs")
    p.add_argument("--once", action="store_true", help="run one cycle and exit")

    p = add("watch", "run queued agent work from the app on this machine",
            lambda a: bridge.watch(a.repository, a.allow_edits, a.push, a.interval, a.timeout,
                                   a.once))  # fmt: skip
    p.add_argument("--allow-edits", action="store_true")
    p.add_argument("--push", action="store_true")
    p.add_argument("--interval", type=int, default=10)
    p.add_argument("--timeout", type=int, default=900)
    p.add_argument("--once", action="store_true")

    p = add("run", "execute one queued agent run",
            lambda a: bridge.run_bridge(a.run_id, a.repository, a.allow_edits, a.timeout, a.push))  # fmt: skip
    p.add_argument("run_id")
    p.add_argument("--allow-edits", action="store_true")
    p.add_argument("--push", action="store_true")
    p.add_argument("--timeout", type=int, default=900)

    add("login", "save this workspace's token for the checkout (once)",
        lambda a: bridge.login(a.repository))  # fmt: skip
    add("logout", "remove the saved token", lambda a: bridge.logout(a.repository))

    args = parser.parse_args(argv)
    try:
        return args.func(args) or 0
    except ValueError as exc:  # Configuration problems from the bridge.
        print(S.red("✗"), exc)
        return 1
    except ApiError as exc:
        print(S.red("✗"), exc)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
