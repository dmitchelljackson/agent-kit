import contextlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent_kit.cli import main  # noqa: E402


@contextlib.contextmanager
def chdir(path: Path):
    old = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


def akit(cwd: Path, *args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with chdir(cwd), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(list(args))
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
    return code, out.getvalue(), err.getvalue()


def make_wiki(root: Path, agents=("claude",)) -> Path:
    """A minimal project with a wiki and no kit."""
    (root / ".agent-kit.json").write_text(json.dumps({"project": "demo", "wiki": "wiki", "agents": list(agents)}))
    (root / "wiki").mkdir()
    (root / "wiki" / "_page.md").write_text("---\ntitle: Home\n---\n")
    return root


class TempDir:
    def __enter__(self) -> Path:
        self._td = tempfile.TemporaryDirectory()
        return Path(self._td.name).resolve()

    def __exit__(self, *exc):
        self._td.cleanup()
