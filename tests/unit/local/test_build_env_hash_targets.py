import os
import pytest
from pathlib import Path
from makei.build import BuildEnv
from makei.rules_mk import RulesMk
from tests.lib.const import DATA_PATH

# Tests for BuildEnv._check_target_needs_rebuild, which only runs for # or $ named
# targets. It decides whether a target is stale by comparing the source's timestamp
# against the built object's, and locates the source from its extension: an extension
# naming an object type is assumed to be an already built object and is looked for in
# the object library, otherwise the source is looked for in the source directory.
#
# That is right for a recipe whose source really is a built object, such as
#
#   S\#DATE.PGM: S\#DATE.MODULE
#
# but wrong for a pseudo-source recipe, which reads its source from an IFS file whose
# extension happens to name an object type
#
#   S\#SRVPGM.BNDDIR: S\#SRVPGM.BNDDIR
#
# Here the source resolves onto the object itself, so the check asks whether the object
# is newer than itself. That is never true, so the object is built once and then never
# rebuilt from source. Affects BNDDIR, CMD, DTAARA, DTAQ and MSGF.


@pytest.fixture
def set_test_directory(request):
    original_cwd = Path.cwd()
    project_name = request.param
    test_dir = Path(f"{DATA_PATH}/build_env/{project_name}").resolve()
    os.chdir(test_dir)
    try:
        yield test_dir
    finally:
        os.chdir(original_cwd)


def get_rule(test_dir: Path, target: str):
    # Rule targets are escaped, e.g. S\#SRVPGM.BNDDIR, so unescape before matching.
    rules_mk = RulesMk.from_file(test_dir / "Rules.mk", test_dir)
    return next(rule for rule in rules_mk.rules if rule.target.replace("\\#", "#") == target)


def set_mtime_after(path: Path, other: Path):
    # Set the timestamp explicitly rather than by write order, which filesystems with a
    # coarse timestamp granularity do not guarantee.
    newer = other.stat().st_mtime + 10
    os.utime(path, (newer, newer))


@pytest.mark.parametrize("target", [
    "S#SRVPGM.BNDDIR",
    "S#ORDERS.DTAQ",
    "S#LASTORD.DTAARA",
    "S#MSGS.MSGF",
    "S#CMD.CMD",
])
@pytest.mark.parametrize("set_test_directory", ["hash_project"], indirect=True)
def test_pseudo_src_rebuilds_when_source_is_newer(set_test_directory, target, tmp_path):
    # An edited pseudo-source must mark its object for rebuild. The object was created
    # once and then never rebuilt, because the source was looked for in the object
    # library instead of the source directory.
    test_dir = set_test_directory
    objlib_path = tmp_path / "OBJLIB.LIB"
    objlib_path.mkdir()
    built_object = objlib_path / target
    built_object.write_text("built object")
    set_mtime_after(test_dir / target, built_object)

    try:
        build_env = BuildEnv()
        rule = get_rule(test_dir, target)
        assert build_env._check_target_needs_rebuild(rule, objlib_path) is True
    finally:
        if build_env:
            build_env._post_make()


@pytest.mark.parametrize("target", [
    "S#SRVPGM.BNDDIR",
    "S#ORDERS.DTAQ",
    "S#LASTORD.DTAARA",
    "S#MSGS.MSGF",
    "S#CMD.CMD",
])
@pytest.mark.parametrize("set_test_directory", ["hash_project"], indirect=True)
def test_pseudo_src_up_to_date_when_source_is_older(set_test_directory, target, tmp_path):
    # An untouched pseudo-source must leave its object alone, so that a fix does not
    # over correct into always rebuilding.
    test_dir = set_test_directory
    objlib_path = tmp_path / "OBJLIB.LIB"
    objlib_path.mkdir()
    built_object = objlib_path / target
    built_object.write_text("built object")
    set_mtime_after(built_object, test_dir / target)

    try:
        build_env = BuildEnv()
        rule = get_rule(test_dir, target)
        assert build_env._check_target_needs_rebuild(rule, objlib_path) is False
    finally:
        if build_env:
            build_env._post_make()


@pytest.mark.parametrize("set_test_directory", ["hash_project"], indirect=True)
def test_object_dependency_resolves_under_objlib(set_test_directory, tmp_path):
    # S\#DATE.PGM: S\#DATE.MODULE depends on a built MODULE, not an IFS file, so a newly
    # recompiled MODULE must mark the PGM for rebuild. This is the case the object
    # library lookup exists to serve and a fix must keep working.
    test_dir = set_test_directory
    objlib_path = tmp_path / "OBJLIB.LIB"
    objlib_path.mkdir()
    built_program = objlib_path / "S#DATE.PGM"
    built_program.write_text("built program")
    dependency_module = objlib_path / "S#DATE.MODULE"
    dependency_module.write_text("recompiled module")
    set_mtime_after(dependency_module, built_program)

    try:
        build_env = BuildEnv()
        rule = get_rule(test_dir, "S#DATE.PGM")
        assert build_env._check_target_needs_rebuild(rule, objlib_path) is True
    finally:
        if build_env:
            build_env._post_make()


@pytest.mark.parametrize("set_test_directory", ["hash_project"], indirect=True)
def test_ordinary_source_resolves_under_source_dir(set_test_directory, tmp_path):
    # S\#HELLO.PGM: S\#HELLO.PGM.RPGLE is the ordinary compile path, where the extension
    # does not name an object type. It is unaffected by the pseudo-source bug and a fix
    # must keep it working.
    test_dir = set_test_directory
    objlib_path = tmp_path / "OBJLIB.LIB"
    objlib_path.mkdir()
    built_program = objlib_path / "S#HELLO.PGM"
    built_program.write_text("built program")
    set_mtime_after(test_dir / "S#HELLO.PGM.RPGLE", built_program)

    try:
        build_env = BuildEnv()
        rule = get_rule(test_dir, "S#HELLO.PGM")
        assert build_env._check_target_needs_rebuild(rule, objlib_path) is True
    finally:
        if build_env:
            build_env._post_make()
