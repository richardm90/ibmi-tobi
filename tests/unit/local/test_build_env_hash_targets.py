import os
import pytest
from pathlib import Path
from makei.build import BuildEnv
from makei.const import TARGET_TARGETGROUPS_MAPPING
from makei.rules_mk import RulesMk
from makei.utils import escape_special_chars
from tests.lib.const import DATA_PATH

# Tests for BuildEnv._check_target_needs_rebuild, which only runs for # or $ named
# targets. It decides whether a target is stale by comparing what the target is built
# from against the built object, so it first has to work out where that input lives.
#
# A target can be built from another object, which is in the object library:
#
#   S\#DATE.PGM: S\#DATE.MODULE
#
# or from a file, which is in the source directory:
#
#   S\#SRVPGM.BNDDIR: S\#SRVPGM.BNDDIR
#
# It used to tell the two apart by the input's extension, which is wrong for a
# pseudo-source recipe: those read their source from a source directory file whose
# extension names an object type, so the source resolved onto the object itself and the
# check asked whether the object was newer than itself. That is never true, so the object
# was built once and then never rebuilt from source. It affected BNDDIR, CMD, DTAARA,
# DTAQ and MSGF.


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
    # An untouched pseudo-source must leave its object alone. The counterpart to the test
    # above: resolving the source correctly must not turn into rebuilding unconditionally.
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
    # S\#DATE.PGM: S\#DATE.MODULE is built from a MODULE object in the library rather than
    # from a source directory file, so a newly recompiled MODULE must mark the PGM for
    # rebuild. This is the case the object library lookup exists to serve.
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


@pytest.mark.parametrize("target", [
    "S#SRVPGM.BNDDIR",
    "S#ORDERS.DTAQ",
    "S#LASTORD.DTAARA",
    "S#MSGS.MSGF",
    "S#CMD.CMD",
])
@pytest.mark.parametrize("set_test_directory", ["hash_project"], indirect=True)
def test_pseudo_src_transitive_dependency_key_is_the_target_itself(set_test_directory, target):
    # The transitive dependency loop in _create_build_vars marks a target for rebuild when
    # the object it is built from is itself being rebuilt. It decides whether that input
    # is an object by its extension, so a pseudo-source, whose source is a source
    # directory file with an object type extension, is treated as one.
    #
    # That does nothing here. The loop looks the input up in special_char_files by escaped
    # name, which for a pseudo-source is the target's own key, and only acts when that
    # entry is True - but targets already marked True are skipped before the lookup is
    # reached. So the branch can never fire for a pseudo-source.
    test_dir = set_test_directory
    rule = get_rule(test_dir, target)

    try:
        build_env = BuildEnv()
        source_file = build_env._unescape_special_chars(rule.source_file.replace('$(d)/', ''))
        escaped_dependency = build_env._escape_special_chars_internal(source_file)
        escaped_target = escape_special_chars(rule.target)

        # The extension names an object type, so the loop's branch is entered ...
        assert source_file.upper().split('.')[-1] in TARGET_TARGETGROUPS_MAPPING
        # ... but the dependency it looks up is the target itself.
        assert escaped_dependency == escaped_target
    finally:
        if build_env:
            build_env._post_make()


@pytest.mark.parametrize("set_test_directory", ["hash_project"], indirect=True)
def test_object_dependency_transitive_key_is_the_dependency(set_test_directory):
    # A target built from a real object resolves to a different key, so the lookup finds
    # another target's entry and the loop does what it is for: S\#DATE.PGM is marked for
    # rebuild when S\#DATE.MODULE is.
    test_dir = set_test_directory
    rule = get_rule(test_dir, "S#DATE.PGM")

    try:
        build_env = BuildEnv()
        source_file = build_env._unescape_special_chars(rule.source_file.replace('$(d)/', ''))
        escaped_dependency = build_env._escape_special_chars_internal(source_file)
        escaped_target = escape_special_chars(rule.target)

        assert source_file.upper().split('.')[-1] in TARGET_TARGETGROUPS_MAPPING
        assert escaped_dependency != escaped_target
        assert escaped_dependency == "SHASHESCAPE_DATE.MODULE"
    finally:
        if build_env:
            build_env._post_make()


@pytest.mark.parametrize("set_test_directory", ["hash_project"], indirect=True)
def test_ordinary_source_resolves_under_source_dir(set_test_directory, tmp_path):
    # S\#HELLO.PGM: S\#HELLO.PGM.RPGLE is the ordinary compile path: a target built from a
    # source file whose extension does not name an object type.
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
