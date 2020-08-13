import repo_config
import re
MU2E_BOT_USER = repo_config.CMSBUILD_USER #"FNALbuild"

# all default tests
TEST_REGEXP_MU2E_DEFTEST_TRIGGER = (
    "(@%s)(\s*[,:;]*\s+|\s+)(please\s*[,]*\s+|)(run\s+test(s|)|test)(\.|$)" % MU2E_BOT_USER
)
REGEX_DEFTEST_MU2E_PR = re.compile(TEST_REGEXP_MU2E_DEFTEST_TRIGGER, re.I | re.M)

# build test
TEST_REGEXP_MU2E_BUILDTEST_TRIGGER = (
    "(@%s)(\s*[,:;]*\s+|\s+)(please\s*[,]*\s+|)(run\s+(build\s*)test(s|)|(test\s+(build)))"
    % MU2E_BOT_USER
)
REGEX_BUILDTEST_MU2E_PR = re.compile(TEST_REGEXP_MU2E_BUILDTEST_TRIGGER, re.I | re.M)

# code test
TEST_REGEXP_MU2E_LINTTEST_TRIGGER = (
    "(@%s)(\s*[,:;]*\s+|\s+)(please\s*[,]*\s+|)(run\s+(code\s*)(test(s|)|check(s|)))"
    % MU2E_BOT_USER
)
REGEX_LINTTEST_MU2E_PR = re.compile(TEST_REGEXP_MU2E_LINTTEST_TRIGGER, re.I | re.M)

# physics validation
TEST_REGEXP_MU2E_VALIDATION_TRIGGER = (
    "(@%s)(\s*[,:;]*\s+|\s+)(please\s*[,]*\s+|)(run\s+validation)" % MU2E_BOT_USER
)
REGEX_VALIDATIONTEST_MU2E_PR = re.compile(TEST_REGEXP_MU2E_VALIDATION_TRIGGER, re.I | re.M)

TEST_REGEXP_CUSTOM_TEST_TRIGGER = (
    "(@%s)(\s*[,:;]*\s+|\s+)(please\s*[,]*\s+|)(run\s+tests\s+|run\s+)(.+)(,\s*.+)*(\.|$)" % MU2E_BOT_USER
)
REGEX_CUSTOM_TEST_MU2E_PR = re.compile(TEST_REGEXP_CUSTOM_TEST_TRIGGER, re.I | re.M)

TEST_MENTIONED = (
    "(@%s)(\s*[,:;]*\s+|\s+)" % MU2E_BOT_USER
)
regex_mentioned = re.compile(TEST_MENTIONED, re.I | re.M)


SUPPORTED_TESTS = ['build', 'code checks', 'validation']
DEFAULT_TESTS = ['build']


TEST_ALIASES = {
    'build': ['mu2e/buildtest'],
    'code checks': ['mu2e/codechecks'],
    'validation': ['mu2e/validation']
}

def get_test_name(alias):
    for k, vals in TEST_ALIASES.items():
        if alias.lower() in vals or alias.lower() == k:
            return k
    return 'unrecognised'

def get_test_alias(test):
    if not test in TEST_ALIASES:
        return 'mu2e/unrecognised'
    return TEST_ALIASES[test][0]

def process_custom_test_request(matched_re):
    testlist = [x.strip() for x in matched_re.group(5).split(',') if x.strip().lower() in SUPPORTED_TESTS]
    print ('tests requested:')
    if len(testlist) == 0:
        return None
    return [testlist, 'current']

def get_tests_for(monorepo_packages):
    # takes a list of top-level folders in Offline and returns
    # the tests required for them
    # returns DEFAULT_TESTS for now

    return DEFAULT_TESTS

def get_stall_time(name):
    return 3600 # tests usually return results within an hour

TESTS  = [
    #[REGEX_CUSTOM_TEST_MU2E_PR, process_custom_test_request],
    [REGEX_BUILDTEST_MU2E_PR, lambda matchre: (['build'], 'current')],
    [REGEX_LINTTEST_MU2E_PR, lambda matchre: (['code checks'], 'current')],
    [REGEX_VALIDATIONTEST_MU2E_PR, lambda matchre: (['validation'], 'current')],
    #[REGEX_DEFTEST_MU2E_PR, lambda matchre: (DEFAULT_TESTS, 'current')],
]
