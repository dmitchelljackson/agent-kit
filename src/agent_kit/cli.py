"""akit — the agent-kit CLI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, adapters, bookmarks, judge, kit
from . import frontmatter as fm
from .config import AkitError, Project, find_project
from .init import init as do_init
from .wiki import PAGE, Wiki


def _ctx() -> tuple[Project, Wiki]:
    p = find_project()
    return p, Wiki(p.wiki)


def _need_project(p: Project, what: str) -> None:
    if p.is_kit:
        raise AkitError(f"`akit {what}` is for projects that use the kit. In the kit repo itself, edit the wiki and open a PR normally.")


def _body(args) -> str:
    if getattr(args, "body_file", None):
        src = sys.stdin if args.body_file == "-" else open(args.body_file, encoding="utf-8")
        with src:
            return src.read()
    return getattr(args, "body", "") or ""


# ---------------- commands ----------------

def cmd_init(a):
    root = Path.cwd()
    agents = [x.strip() for x in a.agents.split(",") if x.strip()] if a.agents else []
    project, log = do_init(root, a.name or root.name, a.summary or "", agents, a.kit, a.wiki, a.force)
    print("\n".join(log))
    if not a.no_install:
        print("\nInstalling agent-kit conventions from the kit...")
        print("\n".join(kit.install(project, ["agent-kit"], recursive=True)))
    w = Wiki(project.wiki)
    print("\n".join(bookmarks.sync(project, w)))
    w.write_index()
    print(f"\nDone. Next: follow the kit's BOOTSTRAP.md (interview, fill AGENTS.md TODOs, install stack pages).")


def cmd_read(a):
    _, w = _ctx()
    failed = []
    for i, t in enumerate(a.targets):
        text, errors = w.render(w.find(t))
        if i:
            print("\n---\n")
        print(text, end="")
        failed += errors
    if failed:
        raise AkitError("broken embeds:\n  " + "\n  ".join(failed))


def cmd_page_new(a):
    _, w = _ctx()
    p = w.new_page(a.path, a.title, a.summary or "")
    w.write_index()
    print(w.rel(p))


def cmd_atom_new(a):
    _, w = _ctx()
    doc = w.new_atom(a.title, w.page_dir(a.page), _body(a), a.name, a.status, not a.no_embed, a.after)
    w.write_index()
    print(f"{doc.id}  {w.rel(doc.path)}")


def cmd_atom_find(a):
    _, w = _ctx()
    p = w.find(a.ref)
    print(w.rel(p))


def cmd_atom_rename(a):
    _, w = _ctx()
    if not a.title and not a.name:
        raise AkitError("Give a new title and/or --name.")
    p = w.rename_atom(a.ref, a.title, a.name)
    print(w.rel(p))


def cmd_atom_move(a):
    _, w = _ctx()
    print(w.rel(w.move_atom(a.ref, w.page_dir(a.page))))


def cmd_atom_rm(a):
    _, w = _ctx()
    path, leftovers = w.remove_atom(a.ref)
    print(f"removed {w.rel(path)}")
    for l in leftovers:
        print(f"note: {l} still links to it (plain [[link]]); fix the prose")


def cmd_index(a):
    _, w = _ctx()
    print(w.rel(w.write_index()))


def cmd_check(a):
    p, w = _ctx()
    probs = [str(x) for x in w.check()]
    probs += [f"ERROR bookmarks: {s}" for s in bookmarks.stale(p, w)]
    for line in probs:
        print(line)
    errors = [x for x in probs if x.startswith("ERROR")]
    print(f"\n{len(errors)} error(s), {len(probs) - len(errors)} warning(s)")
    if errors:
        raise SystemExit(1)


def cmd_log(a):
    _, w = _ctx()
    w.append_log(a.op, a.subject, a.note or "")
    print(f"logged: {a.op} | {a.subject}")


def _wiki_roots(p: Project) -> list[Path]:
    roots = [p.wiki]
    existing = None if p.is_kit else kit.existing_checkout(p)
    if existing:
        roots.append(existing / kit.KIT_WIKI)
    return roots


def _bookmark_packet(p: Project, w: Wiki, page_dir: Path, when: str, evidence: str) -> str:
    rendered, _ = w.render(page_dir / PAGE)
    existing = "\n".join(f"- {b.name}: {b.when}" for b in bookmarks.list_bookmarks(w)
                         if b.page.resolve() != page_dir.resolve()) or "(no other bookmarks)"
    candidate = (f"**Page:** `{w.rel(page_dir)}`\n**Proposed trigger:** {when}\n"
                 f"**Evidence offered:** {evidence or '(none given)'}\n\n### Page content\n\n{rendered}")
    return judge.build_packet("bookmark", judge.criteria_text(_wiki_roots(p), "bookmark"), candidate,
                              f"Existing bookmarks in this project:\n{existing}")


def cmd_bookmark_add(a):
    p, w = _ctx()
    d = w.page_dir(a.page)
    when = a.when or fm.load(d / PAGE).meta.get("bookmark")
    if not when:
        raise AkitError('Give --when "Use before ..." (the moment this page must be read).')
    approval = judge.decide("bookmark", lambda: _bookmark_packet(p, w, d, when, a.evidence or ""), p, a.owner, a.verdict, a.judge)
    bookmarks.set_bookmark(w, d, when, approval, a.name)
    print("\n".join(bookmarks.sync(p, w)))
    w.write_index()
    w.append_log("bookmark", f"{w.rel(d)}: {when}", f"Approval: {approval}")


def cmd_bookmark_ls(a):
    _, w = _ctx()
    for b in bookmarks.list_bookmarks(w):
        print(f"{b.name:32} {w.rel(b.page):32} {b.when}  [{b.approval or '?'}]")


def cmd_bookmark_rm(a):
    p, w = _ctx()
    d = w.page_dir(a.page)
    bookmarks.clear_bookmark(w, d)
    print("\n".join(bookmarks.sync(p, w)))
    w.write_index()
    w.append_log("bookmark-removed", w.rel(d))


def cmd_bookmark_sync(a):
    p, w = _ctx()
    print("\n".join(bookmarks.sync(p, w)) or "bookmarks up to date")


def cmd_adapters(a):
    try:
        p = find_project()
    except AkitError:
        p = None
    reg = adapters.registry(p)
    for name, spec in reg.items():
        mark = "*" if p and name in p.agents else " "
        ver = "verified" if spec.get("verified") else "unverified"
        print(f"{mark} {name:9} skills: {spec.get('skills_dir') or '-':18} judge: {spec.get('judge') or '-'}  ({ver})")
    chosen = judge.resolve_command(p)
    print(f"\njudge in use: {chosen[0] + ' → ' + chosen[1] if chosen else 'none (packet-file flow)'}")


def cmd_kit_ls(a):
    p, _ = _ctx()
    for rel, title, summary, have in kit.available(p):
        depth = rel.count("/")
        print(f"{'✓' if have else ' '} {'  ' * depth}{rel:40} {title}{' — ' + summary if summary else ''}")


def cmd_install(a):
    p, w = _ctx()
    _need_project(p, "install")
    print("\n".join(kit.install(p, a.pages, a.recursive)))
    w = Wiki(p.wiki)
    print("\n".join(bookmarks.sync(p, w)))
    w.write_index()
    w.append_log("install", ", ".join(a.pages), f"From kit commit {p.commit[:12] if p.commit else '?'}")


def cmd_sync(a):
    p, w = _ctx()
    _need_project(p, "sync")
    if a.done:
        h = kit.sync_done(p)
        w.append_log("sync", f"kit -> {h[:12]}")
        print(f"recorded kit commit {h[:12]}")
        return
    if a.take or a.take_safe:
        print("\n".join(kit.sync_take(p, a.take or [], a.take_safe)) or "nothing taken")
        w = Wiki(p.wiki)
        print("\n".join(bookmarks.sync(p, w)))
        w.write_index()
        return
    print(kit.format_report(kit.sync_report(p)))


def _share_packet(p: Project, w: Wiki, targets: list[str], evidence: str, findings: list[str]) -> str:
    parts = []
    for t in targets:
        text, _ = w.render(w.find(t))
        parts.append(text)
    repo = kit.checkout(p, fetch=False)
    index = kit.git("show", f"{kit.head(p, repo)}:{kit.KIT_WIKI}/index.md", cwd=repo, check=False) or "(kit has no index)"
    known = set(Wiki(repo / kit.KIT_WIKI).by_id()) if (repo / kit.KIT_WIKI).exists() else set()
    updates = [d.id for t in targets for d in [fm.load(w.find(t))] if d.id in known]
    context = (f"Kit index (what already exists upstream):\n\n{index}\n\n"
               f"Atoms that update existing kit atoms: {', '.join(updates) or 'none'}\n\n"
               f"Automated scan findings: {'; '.join(findings) or 'none'}\n\n"
               f"Evidence offered: {evidence or '(none given)'}")
    return judge.build_packet("share", judge.criteria_text(_wiki_roots(p), "share"), "\n\n---\n\n".join(parts), context)


def cmd_share(a):
    p, w = _ctx()
    _need_project(p, "share")
    if a.targets[:1] == ["submit"]:
        if not a.title:
            raise AkitError('Give --title "..." for the PR.')
        url = kit.share_submit(a.title, a.draft)
        w.append_log("share", a.title, url)
        print(url)
        return
    files = [path for path, _ in kit.collect(p, a.targets, a.recursive)]
    findings = kit.scan(p, files)
    if findings and not a.accept_findings:
        raise AkitError("Scan found possible secrets or project-specific details:\n  " + "\n  ".join(findings)
                        + "\n\nScrub them, or if the owner reviewed these and wants to share anyway, re-run with --accept-findings.")
    approval = judge.decide("share", lambda: _share_packet(p, w, a.targets, a.evidence or "", findings), p, a.owner, a.verdict, a.judge)
    st = kit.share_prepare(p, a.targets, a.recursive, approval, findings if a.accept_findings else [])
    print(f"Prepared branch {st['branch']} in {st['worktree']}")
    for c in st["changes"]:
        print(f"  {c['kind']:10} {c['path']}")
    if st["problems"]:
        print("\nKit check errors after applying (fix in the worktree before submitting):\n  " + "\n  ".join(st["problems"]))
    print(f"\nNext: fill every TODO(akit) in the PR body:\n  {st['body']}\nthen run: akit share submit --title \"<title>\"")


def cmd_judge(a):
    p, w = _ctx()
    if a.kind == "bookmark":
        d = w.page_dir(a.targets[0])
        when = a.when or fm.load(d / PAGE).meta.get("bookmark") or "(no trigger given)"
        packet = _bookmark_packet(p, w, d, when, a.evidence or "")
    else:
        files = [path for path, _ in kit.collect(p, a.targets, False)]
        packet = _share_packet(p, w, a.targets, a.evidence or "", kit.scan(p, files))
    if a.print:
        print(packet)
        return
    v, out = judge.run(a.kind, packet, p, a.judge)
    print(out if v else f"No judge configured; packet written to {out}")


# ---------------- parser ----------------

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="akit", description="agent-kit: an atom-based wiki, bookmarks, and sharing for coding agents.")
    ap.add_argument("--version", action="version", version=f"akit {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="set up this project (config, AGENTS.md, wiki/, raw/)")
    s.add_argument("--name"); s.add_argument("--summary")
    s.add_argument("--agents", help="comma list: claude,codex,opencode,gemini,...")
    s.add_argument("--kit", help="kit repo URL (default: dmitchelljackson/agent-kit)")
    s.add_argument("--wiki", default="wiki"); s.add_argument("--force", action="store_true")
    s.add_argument("--no-install", action="store_true", help="don't pull the agent-kit conventions pages")
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("read", help="print a page (or atom) with every embed inlined")
    s.add_argument("targets", nargs="+", help="page dir, atom id/name, or file"); s.set_defaults(fn=cmd_read)

    pg = sub.add_parser("page", help="page operations").add_subparsers(dest="sub", required=True)
    s = pg.add_parser("new", help="create a page (folder + _page.md)")
    s.add_argument("path", help="wiki-relative path, e.g. android/testing"); s.add_argument("title")
    s.add_argument("--summary"); s.set_defaults(fn=cmd_page_new)

    at = sub.add_parser("atom", help="atom operations (IDs are generated for you)").add_subparsers(dest="sub", required=True)
    s = at.add_parser("new", help="create an atom and embed it in a page")
    s.add_argument("title"); s.add_argument("--page", required=True)
    s.add_argument("--body", help="atom body text"); s.add_argument("--body-file", help="read body from file ('-' = stdin)")
    s.add_argument("--name", help="file name (default: from title)"); s.add_argument("--status", choices=["locked", "derived", "open", "later"])
    s.add_argument("--after", help="insert the embed after this atom"); s.add_argument("--no-embed", action="store_true")
    s.set_defaults(fn=cmd_atom_new)
    s = at.add_parser("find", help="print an atom's file path"); s.add_argument("ref"); s.set_defaults(fn=cmd_atom_find)
    s = at.add_parser("rename", help="retitle/rename an atom and rewrite every embed")
    s.add_argument("ref"); s.add_argument("title", nargs="?"); s.add_argument("--name"); s.set_defaults(fn=cmd_atom_rename)
    s = at.add_parser("move", help="move an atom to another page"); s.add_argument("ref"); s.add_argument("--page", required=True)
    s.set_defaults(fn=cmd_atom_move)
    s = at.add_parser("rm", help="delete an atom and its embeds"); s.add_argument("ref"); s.set_defaults(fn=cmd_atom_rm)

    sub.add_parser("index", help="regenerate wiki/index.md").set_defaults(fn=cmd_index)
    sub.add_parser("check", help="lint the wiki and bookmarks").set_defaults(fn=cmd_check)
    s = sub.add_parser("log", help="append a log entry"); s.add_argument("op"); s.add_argument("subject")
    s.add_argument("--note"); s.set_defaults(fn=cmd_log)

    bm = sub.add_parser("bookmark", help="bookmark skills").add_subparsers(dest="sub", required=True)
    s = bm.add_parser("add", help="bookmark a page (runs the bookmark judge unless --owner)")
    s.add_argument("page"); s.add_argument("--when", help='"Use before ..."'); s.add_argument("--name", help="skill name override")
    s.add_argument("--evidence", help="the mistake or near-miss that justifies it")
    s.add_argument("--owner", action="store_true", help="the owner explicitly asked for this; skip the judge")
    s.add_argument("--verdict", help="verdict line from a judge subagent"); s.add_argument("--judge", help="agent name or command")
    s.set_defaults(fn=cmd_bookmark_add)
    bm.add_parser("ls", help="list bookmarks").set_defaults(fn=cmd_bookmark_ls)
    s = bm.add_parser("rm", help="remove a page's bookmark"); s.add_argument("page"); s.set_defaults(fn=cmd_bookmark_rm)
    bm.add_parser("sync", help="regenerate skill files from pages").set_defaults(fn=cmd_bookmark_sync)

    s = sub.add_parser("judge", help="run (or print) a judge packet without acting")
    s.add_argument("kind", choices=["bookmark", "share"]); s.add_argument("targets", nargs="+")
    s.add_argument("--when"); s.add_argument("--evidence"); s.add_argument("--judge")
    s.add_argument("--print", action="store_true", help="print the packet instead of running it")
    s.set_defaults(fn=cmd_judge)

    sub.add_parser("adapters", help="list agent adapters and the judge in use").set_defaults(fn=cmd_adapters)

    k = sub.add_parser("kit", help="browse the kit").add_subparsers(dest="sub", required=True)
    k.add_parser("ls", help="list pages available in the kit").set_defaults(fn=cmd_kit_ls)

    s = sub.add_parser("install", help="copy kit pages into this project")
    s.add_argument("pages", nargs="+"); s.add_argument("--recursive", "-r", action="store_true"); s.set_defaults(fn=cmd_install)

    s = sub.add_parser("sync", help="report upstream kit changes; take the ones you want")
    s.add_argument("--take", nargs="+", metavar="ID|PAGE"); s.add_argument("--take-safe", action="store_true",
                                                                          help="take everything unchanged locally")
    s.add_argument("--done", action="store_true", help="record the latest kit commit as synced")
    s.set_defaults(fn=cmd_sync)

    s = sub.add_parser("share", help="propose pages/atoms to the kit as a PR (`akit share submit` to open it)")
    s.add_argument("targets", nargs="+", help="pages or atoms; or 'submit'")
    s.add_argument("--recursive", "-r", action="store_true")
    s.add_argument("--evidence", help="why this is general; what went wrong")
    s.add_argument("--owner", action="store_true", help="the owner explicitly asked to share this; skip the judge")
    s.add_argument("--verdict"); s.add_argument("--judge")
    s.add_argument("--accept-findings", action="store_true", help="owner reviewed scan findings and accepts them")
    s.add_argument("--title", help="PR title (submit)"); s.add_argument("--draft", action="store_true")
    s.set_defaults(fn=cmd_share)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.fn(args)
    except AkitError as e:
        print(f"akit: {e}", file=sys.stderr)
        return e.exit_code
    except BrokenPipeError:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
