PR_SALUTATION = """Hi @{pr_author},
You have proposed changes to files in these packages:
{changed_folders}

which require these tests: {tests_required}.

{auth_teams} have access to CI actions on [{base_branch}](/Mu2e/Offline/tree/{base_branch}).

{watchers}

{non_member_msg}

{tests_triggered_msg}

[About FNALbuild.](https://mu2ewiki.fnal.gov/wiki/Git#GitHub_Pull_Request_Procedures_and_FNALbuild) [Code review on Mu2e/Offline.](https://mu2ewiki.fnal.gov/wiki/GitHubWorkflow#Code_Review)
"""

TESTS_TRIGGERED_CONFIRMATION = """:hourglass: The following tests have been triggered for {commit_link}: {test_list} {tests_already_running_msg} (Build queue {build_queue_str})
"""

TESTS_ALREADY_TRIGGERED = """:x: Those tests have already run or are running for {commit_link} ({triggered_tests})"""

PR_AUTHOR_NONMEMBER = """:memo: The author of this pull request is not a member of the [Mu2e github organisation](https://github.com/Mu2e)."""

JOB_STALL_MESSAGE = """:question: The {joblist} job(s) have failed or timed out on Jenkins, as there has been no result for over an hour.

{info}

The tests may now be triggered again.

"""
BASE_BRANCH_HEAD_CHANGED = ":memo: The HEAD of `{base_ref}` has changed to {base_sha}. Tests are now out of date."
