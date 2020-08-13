from __future__ import print_function

import re, time, os
from datetime import datetime
from os.path import join, exists
from os import environ
from github_utils import get_token, edit_pr, api_rate_limits
from socket import setdefaulttimeout
from _py2with3compatibility import run_cmd

from github import Github

setdefaulttimeout(300)


PR_SALUTATION =  """Hi @{pr_author},
You have proposed changes to files in these packages:
{changed_folders}

which require these tests: {tests_required}.

{watchers}
{tests_triggered_msg}

<a href="https://mu2ewiki.fnal.gov/wiki/Git#GitHub_Pull_Request_Procedures_and_FNALbuild">FNALbuild is explained here.</a>
"""

TESTS_TRIGGERED_CONFIRMATION = """:hourglass: The following tests have been triggered for ref {commit_link}: {test_list} {tests_already_running_msg}"""
TESTS_ALREADY_TRIGGERED = """:x: Those tests have already run or are running for ref {commit_link} ({triggered_tests})"""


# Mu2e triggering statements are in 'test_suites.py'
import test_suites

def check_test_cmd_mu2e(full_comment, repository):
    # we have a suite of regex statements to support triggering all kinds of tests.
    # each item in this list matches a trigger statement in a github comment

    # each 'trigger event' function should return:
    # (testnames to run: list, master+branchPR merge result to run them on)

    # tests:
    # desc: code checks -> mu2e/codechecks (context name) -> [jenkins project name]
    # desc: integration build tests -> mu2e/buildtest -> [jenkins project name]
    # desC: physics validation -> mu2e/validation -> [jenkins project name]
    print (" ====== matching regex to comment ======")
    try:
        print (repr(full_comment))
    except:
        print("could not print comment...")

    for regex, handler in test_suites.TESTS:
        # returns the first match in the comment
        match = regex.search(full_comment)
        if match is None:
            print (regex.pattern, "NOT MATCHED")
            continue
        handle = handler(match)

        if handle is None:
            print (regex.pattern, "MATCHED - BUT NoneType HANDLE RETURNED")
            continue
        print (regex.pattern, "MATCHED")
        return handle, True

    if test_suites.regex_mentioned.search(full_comment) is not None:
        print ("MATCHED - but unrecognised command")
        return None, True
    print ("NO MATCHES")
 
    return None, False

# Read a yaml file
def read_repo_file(repo_config, repo_file, default=None):
    import yaml

    file_path = join(repo_config.CONFIG_DIR, repo_file)
    contents = default
    if exists(file_path):
        contents = yaml.load(open(file_path,'r'), Loader=yaml.FullLoader)
        if not contents:
            contents = default
    return contents

def create_property_file(out_file_name, parameters, dryRun):
    if dryRun:
        print("Not creating cleanup properties file (dry-run): %s" % out_file_name)
        return
    print("Creating properties file %s" % out_file_name)
    out_file = open(out_file_name, "w")
    for k in parameters:
        out_file.write("%s=%s\n" % (k, parameters[k]))
    out_file.close()

def create_properties_file_for_test(test, repository, pr_number, pr_commit_sha, master_commit_sha, dryRun=False):
    repo_partsX = repository.replace("/", "-") # mu2e/Offline ---> mu2e-Offline
    out_file_name = "trigger-mu2e-%s-%s-%s.properties" % (test.replace(' ', '-'), repo_partsX, pr_number)

    parameters = {}
    parameters["TEST_NAME"] = test
    parameters["REPOSITORY"] = repository
    parameters["PULL_REQUEST"] = pr_number
    parameters["COMMIT_SHA"] = pr_commit_sha
    parameters["MASTER_COMMIT_SHA"] = master_commit_sha

    create_property_file(out_file_name, parameters, dryRun)


def get_modified(modified_files):
    modified_top_level_folders = []
    for f in modified_files:
        filename, file_extension = os.path.splitext(f.filename)
        print( "Changed file (%s): %s%s" % (file_extension, filename, file_extension) )

        splits = filename.split('/')
        if len(splits) > 1:
            modified_top_level_folders.append(splits[0])
        else:
            modified_top_level_folders.append('/')

    return set(modified_top_level_folders)

def get_authorised_users(gh, repo):
    mu2eorg = gh.get_organization("Mu2e")
    mu2e_write = mu2eorg.get_team_by_slug('write')
    mu2e_write_mems =['ryuwd'] + [mem.login for mem in mu2e_write.get_members()]

    # users authorised to communicate with this bot
    return set(mu2e_write_mems)


def process_pr(repo_config, gh, repo, issue, dryRun, cmsbuild_user=None, force=False):
    api_rate_limits(gh)

    if not issue.pull_request:
        print("Ignoring: Not a PR")
        return

    prId = issue.number
    pr = repo.get_pull(prId)

    if pr.changed_files == 0:
        print("Ignoring: PR with no files changed")
        return

    authorised_users = get_authorised_users(gh, repo)

    print ("Authorised Users: ", authorised_users)

    not_seen_yet = True
    last_time_seen = None
    labels = []

    # commit test states:
    test_statuses = {}
    test_triggered = {}

    # did we already create a commit status?
    test_status_exists = {}

    # tests we'd like to trigger on this commit
    tests_to_trigger = []
    # tests we've already triggered
    tests_already_triggered = []

    # get PR changed libraries / packages
    pr_files = pr.get_files()

    # top-level folders of the Offline 'monorepo'
    # that have been edited by this PR
    modified_top_level_folders = get_modified(pr_files)
    print ('Build Targets changed:')
    print (
        '\n'.join(['- %s' % s for s in modified_top_level_folders])
    )

    # TODO: print modified monorepo package folders in 'greeting' message
    watchers = read_repo_file(repo_config, "watchers.yaml", {})

    print ('watchers:', watchers)

    # get required tests
    test_requirements = test_suites.get_tests_for(modified_top_level_folders)
    print ('Tests required: ', test_requirements)

    # set their status to 'pending' (will be updated shortly after)
    for test in test_requirements:
        test_statuses[test] = 'pending'
        test_triggered[test] = False
        test_status_exists[test] = False

    # this will be the commit of master that the PR is merged
    # into for the CI tests (for a build test this is just the current HEAD.)
    master_commit_sha = pr.base.sha # repo.get_branch("master").commit.sha

    # get latest commit
    last_commit = pr.get_commits().reversed[0]
    git_commit = last_commit.commit
    if git_commit is None:
        return

    last_commit_date = git_commit.committer.date
    print(
        "Latest commit by ",
        git_commit.committer.name,
        " at ",
        last_commit_date,
    )

    print("Latest commit message: ", git_commit.message.encode("ascii", "ignore"))
    print("Latest commit sha: ", git_commit.sha)
    print("Merging into: ",pr.base.ref, pr.base.sha)
    print("PR update time", pr.updated_at)
    print("Time UTC:", datetime.utcnow())

    if last_commit_date > datetime.utcnow():
        print("==== Future commit found ====")
        if (not dryRun) and repo_config.ADD_LABELS:
            labels = [x.name for x in issue.labels]
            if not "future commit" in labels:
                labels.append("future commit")
                issue.edit(labels=labels)
        return

    # now get commit statuses
    # this is how we figure out the current state of tests
    # on the latest commit of the PR.
    commit_status = last_commit.get_statuses()

    # we can translate git commit status API 'state' strings if needed.
    state_labels = {
        'error': 'error',
        'failure': 'failed',
        'success': 'finished',
    }

    state_labels_colors = {
        'error': 'd73a4a',
        'fail': 'd2222d',
        'pending': 'ffbf00',
        'running': 'a4e8f9',
        'success': '238823',
        'finish': '238823',
        'stalled': 'ededed'
    }

    commit_status_time = {}

    for stat in commit_status:
        name = test_suites.get_test_name(stat.context)
        if name == 'unrecognised':
            continue
        if name in commit_status_time and commit_status_time[name] > stat.updated_at:
            continue

        commit_status_time[name] = stat.updated_at

        # error, failure, pending, success
        test_statuses[name] = stat.state
        if stat.state in state_labels:
            test_statuses[name] = state_labels[stat.state]

        test_status_exists[name] = True
        if name in test_triggered and test_triggered[name]: # if already True, don't change it
            continue

        test_triggered[name] = ('has been triggered' in stat.description) or (stat.state == 'success' or stat.state == 'failure')

        # some other labels, gleaned from the description (the status API
        # doesn't support these states)
        if ('running' in stat.description):
            test_statuses[name] = 'running'

        # check if we've stalled
        if (test_statuses[name] in ['running', 'pending']) and (name in test_triggered) and test_triggered[name]:
            if (datetime.utcnow() - stat.updated_at).total_seconds() > test_suites.get_stall_time(name):
                test_triggered[name] = False # the test may be triggered again.
                test_statuses[name] = 'stalled'


        if (stat.context == 'mu2e/buildtest' and stat.description.startswith(':')):
            # this is the commit SHA in master that we merged into
            # this is important if we want to trigger a validation job
            master_commit_sha = stat.description.replace(':','')



    # now process PR comments that come after when
    # the bot last did something, first figuring out when the bot last commented
    pr_author = issue.user.login
    comments = issue.get_comments()
    for comment in comments:
        # loop through once to ascertain when the bot last commented
        if comment.user.login == repo_config.CMSBUILD_USER:
            if last_time_seen is None or last_time_seen < comment.created_at:
                not_seen_yet = False
                last_time_seen = comment.created_at
                print (comment.user.login, last_time_seen)
    print ("Last time seen", last_time_seen)

    # we might not have commented, but e.g. changed a label instead...
    # for event in pr.get_issue_events():
    #     if event.actor.login == repo_config.CMSBUILD_USER and event.event in ['labeled', 'unlabeled']:
    #         if last_time_seen is None or last_time_seen < event.created_at:
    #             last_time_seen = event.created_at
    #             print (last_time_seen, event)
    # print ("Last time seen", last_time_seen)

    # now we process comments
    for comment in comments:
        # Ignore all messages which are before last commit.
        if (comment.created_at < last_commit_date):
            print ("IGNORE COMMENT (before last commit)")
            continue

        # neglect comments we've already responded to
        if last_time_seen is not None and (comment.created_at < last_time_seen):
            print ("IGNORE COMMENT (seen)", comment.user.login, comment.created_at, '<', last_time_seen)
            continue

        # neglect comments by un-authorised users
        if not comment.user.login in authorised_users or comment.user.login == repo_config.CMSBUILD_USER:
            print("IGNORE COMMENT (unauthorised or bot user) - %s." % comment.user.login)
            continue

        for react in comment.get_reactions():
            if react.user.login == repo_config.CMSBUILD_USER:
                print("IGNORE COMMENT (we've seen it and reacted to say we've seen it)", comment.user.login)


        reaction_t = None
        # now look for bot triggers
        # check if the comment has triggered a test
        trigger_search, mentioned = check_test_cmd_mu2e(comment.body, repo.full_name)
        tests_already_triggered = []

        if trigger_search is not None:
            tests, _ = trigger_search
            print ("Triggered! Comment: %s" % comment.body)
            print ('Current test(s): %r' % tests_to_trigger)
            print ('Adding these test(s): %r' % tests )

            for test in tests:
                # check that the test has been triggered on this commit first
                if test in test_triggered and test_triggered[test]:
                        print ("The test has already been triggered for this ref. It will not be triggered again.")
                        tests_already_triggered.append(test)
                        reaction_t = '-1'
                        continue
                else:
                    test_triggered[test] = False

                if not test_triggered[test]: # is the test already running?
                    # ok - now we can trigger the test
                    print ("The test has not been triggered yet. It will now be triggered.")

                    # update the 'state' of this commit
                    test_statuses[test] = 'pending'
                    test_triggered[test] = True

                    # add the test to the queue of tests to trigger
                    tests_to_trigger.append(test)
                    reaction_t = '+1'
        elif mentioned:
            # we didn't recognise any commands!
            reaction_t = 'confused'

        if reaction_t is not None:
            # "React" to the comment to let the user know we have acknowledged their comment!
            comment.create_reaction(reaction_t)


    # now,
    # - trigger tests if indicated (for this specific SHA.)
    # - set the current status for this commit SHA
    # - apply labels according to the state of the latest commit of the PR
    # - make a comment if required

    for test, state in test_statuses.items():
        labels.append('%s %s' % (test, state))

        if test in tests_to_trigger:
            print ("TEST WILL NOW BE TRIGGERED: %s" % test)
            # trigger the test in jenkins
            create_properties_file_for_test(
                test,
                repo.full_name,
                prId,
                git_commit.sha,
                master_commit_sha
            )
            if not dryRun:
                if test == 'build':
                    # we need to store somewhere the master commit SHA
                    # that we merge into for the build test (for validation)
                    # this is overlapped with the next, more human readable message
                    last_commit.create_status(
                            state="pending",
                            target_url="https://github.com/mu2e/Offline",
                            description=":%s" % master_commit_sha,
                            context=test_suites.get_test_alias(test)
                    )

                last_commit.create_status(
                            state="pending",
                            target_url="https://github.com/mu2e/Offline",
                            description="The test has been triggered in Jenkins",
                            context=test_suites.get_test_alias(test)
                        )
            print ("Git status created for SHA %s test %s - since the test has been triggered." % (git_commit.sha, test))
        elif state == 'pending' and test_status_exists[test]:
            print ("Git status unchanged for SHA %s test %s - the existing one is up-to-date." % (git_commit.sha, test))

        elif state == 'pending' and not test_triggered[test] and not test_status_exists[test]:
            print (test_status_exists)
            print ("Git status created for SHA %s test %s - since there wasn't one already." % (git_commit.sha, test))
            # indicate that the test is pending but
            # we're still waiting for someone to trigger the test
            if not dryRun:
                last_commit.create_status(
                            state="pending",
                            target_url="https://github.com/mu2e/Offline",
                            description="This test has not been triggered yet.",
                            context=test_suites.get_test_alias(test)
                        )
        # don't do anything else with commit statuses
        # the script handler that handles Jenkins job results will update the commits accordingly

    # check if labels have changed
    labelnames =  [x.name for x in issue.labels]
    if (set(labelnames) != set(labels)):
        if not dryRun:
            issue.edit(labels=labels)
        print ("Labels have changed to: ", labels)

    # check label colours
    try:
        for label in issue.labels:
            if label.color == 'ededed':
                # the label color isn't set
                for labelcontent, col in state_labels_colors.items():
                    if labelcontent in label.name:
                        label.edit(label.name, col)
                        break
    except:
        print ("Failed to set label colours!")


    # construct a reply if tests have been triggered.
    tests_triggered_msg = ''
    already_running_msg = ''
    commitlink = 'https://github.com/%s/pull/%s/commits/%s' % (repo.full_name, prId, git_commit.sha)

    if len(tests_to_trigger) > 0:
        if len(tests_already_triggered) > 0:
            already_running_msg = '(already triggered: %s)' % ','.join(tests_already_triggered)

        tests_triggered_msg = TESTS_TRIGGERED_CONFIRMATION.format(
            commit_link=commitlink,
            test_list=', '.join(tests_to_trigger),
            tests_already_running_msg=already_running_msg
        )


    # decide if we should issue a comment, and what comment to issue
    if not_seen_yet:
        print ("First time seeing this PR - send the user a salutation!")
        if not dryRun:
            issue.create_comment(PR_SALUTATION.format(
                pr_author=pr_author,
                changed_folders='\n'.join(['- %s' % s for s in modified_top_level_folders]),
                tests_required=', '.join(test_requirements),
                watchers='',
                tests_triggered_msg=tests_triggered_msg
            ))

    elif len(tests_to_trigger) > 0:
        # tests were triggered, let people know about it
        if not dryRun:
            issue.create_comment(tests_triggered_msg)

    elif len(tests_to_trigger) == 0 and len(tests_already_triggered) > 0:
        if not dryRun:
            issue.create_comment(TESTS_ALREADY_TRIGGERED.format(
                commit_link=commitlink,
                triggered_tests=', '.join(tests_already_triggered))

)
