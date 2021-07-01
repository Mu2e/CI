import re
from Mu2eCI import config
from Mu2eCI.logger import log

MU2E_BOT_USER = config.main["bot"]["username"]  # "FNALbuild"

# all default tests
TEST_REGEXP_MU2E_DEFTEST_TRIGGER = (
    r"(@%s)(\s*[,:;]*\s+|\s+)(please\s*[,]*\s+|)(run\s+test(s|)|test)" % MU2E_BOT_USER
)
REGEX_DEFTEST_MU2E_PR = re.compile(TEST_REGEXP_MU2E_DEFTEST_TRIGGER, re.I | re.M)

# build test
# @FNALbuild build [with #257, #322, ...] [without merge]
# @FNALbuild run build test[s] [with #257, #322, ...] [without merge]
# Group 1: @FNALbuild
# Group 8: [with #257, #322, ...]
# Group 11: [without merge]
TEST_REGEXP_MU2E_BUILDTEST_TRIGGER = (
    rf"(@{MU2E_BOT_USER})(\s*[,:;]*\s+|\s+)"
    r"(please\s*[,]*\s+|)((build)|(run\s+build\s+test(s|)))"
    r"(?P<test_with>\s+with\s+(#[0-9]+([\s,]+|))+|)"
    r"(?P<wo_merge>\s*without\s+merge|)"
)
REGEX_BUILDTEST_MU2E_PR = re.compile(TEST_REGEXP_MU2E_BUILDTEST_TRIGGER, re.I | re.M)

# build test WITH validation
TEST_REGEXP_MU2E_BUILDTEST_TRIGGER_VAL = (
    r"(@%s)(\s*[,:;]*\s+|\s+)(please\s*[,]*\s+|)((build)|(run\s+build\s+test(s|)))(\s+and\s+validat(e|ion))"
    % MU2E_BOT_USER
)
REGEX_BUILDTEST_MU2E_PR_VAL = re.compile(
    TEST_REGEXP_MU2E_BUILDTEST_TRIGGER_VAL, re.I | re.M
)


# code test
TEST_REGEXP_MU2E_LINTTEST_TRIGGER = (
    r"(@%s)(\s*[,:;]*\s+|\s+)(please\s*[,]*\s+|)(run\s+(code\s*)(test(s|)|check(s|)))"
    % MU2E_BOT_USER
)
REGEX_LINTTEST_MU2E_PR = re.compile(TEST_REGEXP_MU2E_LINTTEST_TRIGGER, re.I | re.M)

# physics validation
TEST_REGEXP_MU2E_VALIDATION_TRIGGER = (
    r"(@%s)(\s*[,:;]*\s+|\s+)(please\s*[,]*\s+|)(run\s+validation)" % MU2E_BOT_USER
)
REGEX_VALIDATIONTEST_MU2E_PR = re.compile(
    TEST_REGEXP_MU2E_VALIDATION_TRIGGER, re.I | re.M
)

TEST_REGEXP_CUSTOM_TEST_TRIGGER = (
    r"(@%s)(\s*[,:;]*\s+|\s+)(please\s*[,]*\s+|)(run\s+tests\s+|run\s+)(.+)(,\s*.+)*(\.|$)"
    % MU2E_BOT_USER
)
REGEX_CUSTOM_TEST_MU2E_PR = re.compile(TEST_REGEXP_CUSTOM_TEST_TRIGGER, re.I | re.M)

TEST_MENTIONED = r"(@%s)(\s*[,:;]*\s+|\s+)" % MU2E_BOT_USER
regex_mentioned = re.compile(TEST_MENTIONED, re.I | re.M)

VALID_PR_SPEC = re.compile(r"^(Mu2e\/|)(?P<repo>[A-Za-z0-9_\-]+|)#(?P<pr_id>[0-9]+)$")


SUPPORTED_TESTS = ["build", "code checks", "validation"]
DEFAULT_TESTS = ["build"]

# Whether to trigger the tests in DEFAULT_TESTS when a PR is opened
AUTO_TRIGGER_ON_OPEN = True

TEST_ALIASES = {
    "build": ["mu2e/buildtest"],
    "code checks": ["mu2e/codechecks"],
    "validation": ["mu2e/validation"],
}


def get_test_name(alias):
    for k, vals in TEST_ALIASES.items():
        if alias.lower() in vals or alias.lower() == k:
            return k
    return "unrecognised"


def get_test_alias(test):
    if test not in TEST_ALIASES:
        return "mu2e/unrecognised"
    return TEST_ALIASES[test][0]


def process_custom_test_request(matched_re):
    testlist = [
        x.strip()
        for x in matched_re.group(5).split(",")
        if x.strip().lower() in SUPPORTED_TESTS
    ]
    if len(testlist) == 0:
        return None
    return [testlist, "current"]


def get_tests_for(monorepo_packages):
    # takes a list of top-level folders in Offline and returns
    # the tests required for them
    # returns DEFAULT_TESTS for now

    return DEFAULT_TESTS


def get_stall_time(name):
    return 3600  # tests usually return results within an hour


def build_test_configuration(matched_re):
    # @FNALbuild build [with #257, #322, ...] [without merge]
    # @FNALbuild run build test[s] [with #257, #322, ...] [without merge]
    # @FNALbuild run build test[s] [with Mu2e/Production#257, #322, ...] [without merge]

    test_with = matched_re.group("test_with")
    no_merge = matched_re.group("wo_merge")

    test_with = (
        (test_with.replace("with", "").strip()) if len(test_with.strip()) > 0 else ""
    ).strip()
    log.debug(f"test_with string to process: {test_with}")

    # Each item in the comma separated list must match this:
    # ^(Mu2e|)([A-Za-z0-9_\-]+|)#([0-9]+)$
    prs_to_include = []
    if len(test_with) > 0:
        for test_with_pr in test_with.split(","):
            match = VALID_PR_SPEC.match(test_with_pr.strip())
            if match is None:
                # Bad, or unsanitary PR spec.
                raise ValueError(f"Bad PR specification: {test_with_pr}")
            repository = match.group("repo")
            pr_id = match.group("pr_id")
            prs_to_include.append(f"{repository}#{pr_id}")

    no_merge = "1" if len(no_merge.strip()) > 0 else "0"

    return (
        ["build"],
        "current",
        {"TEST_WITH_PR": ",".join(prs_to_include), "NO_MERGE": no_merge},
    )


TESTS = [
    # [REGEX_CUSTOM_TEST_MU2E_PR, process_custom_test_request],
    [REGEX_BUILDTEST_MU2E_PR, build_test_configuration],
    [REGEX_LINTTEST_MU2E_PR, lambda matchre: (["code checks"], "current", {})],
    [REGEX_VALIDATIONTEST_MU2E_PR, lambda matchre: (["validation"], "current", {})],
    [REGEX_DEFTEST_MU2E_PR, lambda matchre: (DEFAULT_TESTS, "current", {})],
]
