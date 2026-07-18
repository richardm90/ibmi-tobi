import re
import shutil
import subprocess
import pytest
from pathlib import Path
from tests.lib.const import MAKEI_PATH

# Tests for escape_source in src/mk/footer.mk.
#
# Python emits a target's source as either an IFS path carrying the $(d)/ directory
# prefix, or a bare object name for a target built from another object:
#
#   SHASHESCAPE_CMD.CMD_SRC=$(d)/SHASHESCAPE_CMD.CMD     an IFS file
#   SHASHESCAPE_DATE.PGM_SRC=SHASHESCAPE_DATE.MODULE     a built object
#
# escape_source decides whether to turn HASHESCAPE_ back into \# for make. An IFS path
# must be unescaped so make can find the file on disk; an object name must keep its
# escaped form so it matches the target name Python generated for it.
#
# The decision is made on the source's extension, and a pseudo-source recipe reads its
# source from an IFS file whose extension names an object type, so a #-named CMD
# pseudo-source is wrongly treated as an object and left escaped. Make then looks for a
# literal SHASHESCAPE_CMD.CMD file, does not find it, and the target is skipped.

FOOTER_MK = MAKEI_PATH / "src" / "mk" / "footer.mk"

pytestmark = pytest.mark.skipif(shutil.which("make") is None, reason="make is not installed")


def call_escape_source(tmp_path: Path, value: str) -> str:
    """Return what escape_source in footer.mk makes of `value`.

    footer.mk is wrapped in a `define FOOTER` block and cannot be included on its own,
    so the two escaping functions are extracted into a makefile of their own.
    """
    definitions = re.findall(
        r"^define (?:escape_specials|escape_source)$.*?^endef$",
        FOOTER_MK.read_text(encoding="utf8"),
        re.MULTILINE | re.DOTALL,
    )
    makefile = tmp_path / "escape.mk"
    makefile.write_text(
        "\n".join(definitions) + "\nd := QCMDSRC\n"
        "$(info RESULT:$(call escape_source,$(VALUE)))\nall: ; @true\n",
        encoding="utf8",
    )

    result = subprocess.run(
        ["make", "-f", str(makefile), f"VALUE={value}", "all"],
        capture_output=True, text=True, check=True,
    )
    return next(line[len("RESULT:"):] for line in result.stdout.splitlines()
                if line.startswith("RESULT:"))


@pytest.mark.parametrize("source, expected", [
    ("$(d)/SHASHESCAPE_CMD.CMD", "QCMDSRC/S\\#CMD.CMD"),
    ("$(d)/SHASHESCAPE_SRVPGM.BNDDIR", "QCMDSRC/S\\#SRVPGM.BNDDIR"),
    ("$(d)/SHASHESCAPE_ORDERS.DTAQ", "QCMDSRC/S\\#ORDERS.DTAQ"),
    ("$(d)/SHASHESCAPE_LASTORD.DTAARA", "QCMDSRC/S\\#LASTORD.DTAARA"),
    ("$(d)/SHASHESCAPE_MSGS.MSGF", "QCMDSRC/S\\#MSGS.MSGF"),
])
def test_pseudo_src_path_is_unescaped(tmp_path, source, expected):
    # A pseudo-source is an IFS file, so make has to be given the real file name. The
    # CMD case fails: its extension names an object type, so it is left escaped and make
    # looks for a file called SHASHESCAPE_CMD.CMD that does not exist.
    assert call_escape_source(tmp_path, source) == expected


def test_ordinary_source_path_is_unescaped(tmp_path):
    # The ordinary compile path, unaffected by the bug.
    assert call_escape_source(
        tmp_path, "$(d)/SHASHESCAPE_HELLO.PGM.RPGLE") == "QCMDSRC/S\\#HELLO.PGM.RPGLE"


def test_object_source_keeps_its_escaped_form(tmp_path):
    # A target built from another object names that object with no $(d)/ prefix. It has
    # to keep the escaped form so that it matches the target name Python generated, and
    # a fix must not unescape it.
    assert call_escape_source(
        tmp_path, "SHASHESCAPE_DATE.MODULE") == "SHASHESCAPE_DATE.MODULE"
