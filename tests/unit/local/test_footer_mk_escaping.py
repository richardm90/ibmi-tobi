import re
import shutil
import subprocess
import pytest
from pathlib import Path
from tests.lib.const import MAKEI_PATH

# Tests for escape_source in src/mk/footer.mk.
#
# Python emits what a target is built from as either a path carrying the $(d)/ directory
# prefix, or a bare object name:
#
#   SHASHESCAPE_CMD.CMD_SRC=$(d)/SHASHESCAPE_CMD.CMD     a source directory file
#   SHASHESCAPE_DATE.PGM_SRC=SHASHESCAPE_DATE.MODULE     an object in the library
#
# escape_source decides whether to turn HASHESCAPE_ back into \# for make. A path must be
# unescaped so make can find the file on disk; an object name must keep its escaped form
# so it matches the target name Python generated for it.
#
# The decision used to be made on the extension, which a pseudo-source recipe defeats:
# those read their source from a source directory file whose extension names an object
# type, so a #-named CMD pseudo-source was treated as an object and left escaped. Make
# then looked for a literal SHASHESCAPE_CMD.CMD file, did not find it, and skipped the
# target - silently, reporting "0 failed 0 succeed 0 total" and "All targets up-to-date".

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
    # A pseudo-source is a source directory file, so make has to be given the real file
    # name. All five extensions name an object type, which is what made the CMD case go
    # wrong while the other four happened to work.
    assert call_escape_source(tmp_path, source) == expected


def test_ordinary_source_path_is_unescaped(tmp_path):
    # The ordinary compile path, where the extension does not name an object type.
    assert call_escape_source(
        tmp_path, "$(d)/SHASHESCAPE_HELLO.PGM.RPGLE") == "QCMDSRC/S\\#HELLO.PGM.RPGLE"


def test_object_source_keeps_its_escaped_form(tmp_path):
    # A target built from another object names that object with no $(d)/ prefix, and has
    # to keep the escaped form so that it matches the target name Python generated for
    # that object.
    assert call_escape_source(
        tmp_path, "SHASHESCAPE_DATE.MODULE") == "SHASHESCAPE_DATE.MODULE"
