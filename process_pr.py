import re, time, os
from datetime import datetime
from time import sleep, gmtime
from calendar import timegm
from os.path import join, exists
from os import environ
from socket import setdefaulttimeout
from github import Github

import yaml
import test_suites
import repo_config

setdefaulttimeout(300)


PR_SALUTATION =  """Hi @{pr_author},
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

JOB_STALL_MESSAGE = """:question: The {joblist} job(s) have stalled on Jenkins, as there has been no result for 1 hour.

{info}

The tests may now be triggered again.

"""

try: #python3
    from urllib.request import urlopen
except: #python2
    from urllib2 import urlopen
 
import json
def get_build_queue_size():
    jenkins_url = "https://buildmaster.fnal.gov/buildmaster/queue/api/json?pretty=true"
    
    bqsize = "- API unavailable"
    
    try:
        contents = json.load(urlopen(jenkins_url))
        nitems = len(contents['items'])
        bqsize = "is empty"
        if nitems > 0:
            bqsize = "has %d jobs" % nitems
        
    except:
        print("Issues accessing Jenkins Build Queue API")
    return bqsize

# written by CMS-BOT authors
def check_rate_limits(rate_limit, rate_limit_max, rate_limiting_resettime, msg=True):
    doSleep = 0
    rate_reset_sec = rate_limiting_resettime - timegm(gmtime()) + 5
    if msg: print('API Rate Limit: %s/%s, Reset in %s sec i.e. at %s' % (
        rate_limit, rate_limit_max, rate_reset_sec, datetime.fromtimestamp(rate_limiting_resettime)))
    if rate_limit < 100:
        doSleep = rate_reset_sec
    elif rate_limit < 250:
        doSleep = 30
    elif rate_limit < 500:
        doSleep = 10
    elif rate_limit < 750:
        doSleep = 5
    elif rate_limit < 1000:
        doSleep = 2
    elif rate_limit < 1500:
        doSleep = 1
    if (rate_reset_sec < doSleep): doSleep = rate_reset_sec
    if doSleep > 0:
        if msg: print("Slowing down for %s sec due to api rate limits %s approching zero" % (doSleep, rate_limit))
        sleep(doSleep)
    return

# written by CMS-BOT authors
def api_rate_limits(gh, msg=True):
    gh.get_rate_limit()
    check_rate_limits(gh.rate_limiting[0], gh.rate_limiting[1], gh.rate_limiting_resettime, msg)

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
    parameters = {}
    if test == 'build_and_val':
        test = 'build'
        parameters["TRIGGER_VALIDATION"] = '1'
    repo_partsX = repository.replace("/", "-") # mu2e/Offline ---> mu2e-Offline
    out_file_name = "trigger-mu2e-%s-%s-%s.properties" % (test.replace(' ', '-'), repo_partsX, pr_number)

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
def read_repo_file(repo_config, repo_file, default=None):
    import yaml

    file_path = join(repo_config.CONFIG_DIR, repo_file)
    contents = default
    if exists(file_path):
        contents = yaml.load(open(file_path,'r'), Loader=yaml.FullLoader)
        if not contents:
            contents = default
    return contents

def get_authorised_users(mu2eorg, repo, branch='all'):
    file_path = join(repo_config.CONFIG_DIR, 'auth_teams.yaml')
    yaml_contents = {}
    with open(file_path, 'r') as f:
        yaml_contents = yaml.load(open(file_path,'r'), Loader=yaml.FullLoader)
    authed_users = []
    authed_teams = yaml_contents['all'] 
    if branch in yaml_contents:
        authed_teams += yaml_contents[branch]
    
    authed_teams = set(authed_teams)
    print("Authorised Teams: ", authed_teams)
    
    for team_slug in authed_teams:
        teamobj = mu2eorg.get_team_by_slug(team_slug)
        authed_users += [mem.login for mem in teamobj.get_members()]
    
    # users authorised to communicate with this bot
    return set(authed_users), authed_teams

def post_on_pr(issue, comment, previous_bot_comments):
    if comment in previous_bot_comments:
        print("SPAM PROTECTION - We are posting something we already posted before! Something is wrong!")
        return
    issue.create_comment(comment)


def process_pr(repo_config, gh, repo, issue, dryRun, cmsbuild_user=None, force=False, child_call=0):
    if child_call > 2:
        print("Stopping recursion")
        return
    api_rate_limits(gh)

    if not issue.pull_request:
        print("Ignoring: Not a PR")
        return

    prId = issue.number
    pr = repo.get_pull(prId)

    if pr.changed_files == 0:
        print("Ignoring: PR with no files changed")
        return
    
    # GitHub should send a pull_request webhook to Jenkins if the PR is merged.
    if pr.merged:
        # check that this PR was merged recently before proceeding
        # process_pr is triggered on all other open PRs
        # unless this PR was merged more than two minutes ago
        
        # Note: If the Jenkins queue is inundated, then it's likely this won't
        # work at the time. But, this is not likely to be more than just an intermittent problem.
        # This allows for a 2 minute lag.
        if (datetime.utcnow() - pr.merged_at).total_seconds() < 120:
            # Let people know on other PRs that (since this one was merged) the 
            # base ref HEAD will have changed
            print("Triggering check on all other open PRs as this PR was merged within the last 2 minutes.")
            pulls_to_check = repo.get_pulls(state='open', base=pr.base.ref)
            for pr_ in pulls_to_check:
                # Call process_pr within process_pr, while incrementing child_call as a
                # precautionary measure to avoid runaway recursion (for whatever reason) 
                # although I don't forsee that ever happening
                process_pr(repo_config, gh, repo, pr_.as_issue(), dryRun,
                           cmsbuild_user=cmsbuild_user, force=force, child_call=child_call+1)
    
    if pr.state == 'closed':
        print("Ignoring: PR in closed state")
        return
    
    mu2eorg = gh.get_organization("Mu2e")
    trusted_user = mu2eorg.has_in_members(issue.user)

    # if not trusted_user:
    #     print ('Ignoring: PR not from an organisation member')
    #     if not 'CI unavailable' in [x.name for x in issue.labels]:
    #         issue.create_comment(PR_AUTHOR_NONMEMBER)
    #         issue.edit(labels=['CI unavailable'])
    #     return

    authorised_users, authed_teams = get_authorised_users(mu2eorg, repo, branch=pr.base.ref)

    # allow the PR author to execute CI actions:
    if trusted_user:
        authorised_users.add(issue.user.login)

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

    watchers = read_repo_file(repo_config, "watchers.yaml", {})

    # Figure out who is watching the modified packages and notify them
    print ('watchers:', watchers)
    watcher_text = ''
    watcher_list = []
    try:
        modified_targs = [x.lower() for x in modified_top_level_folders]
        for user, packages in watchers.items():
            for pkgpatt in packages:
                try:
                    regex_comp = re.compile(pkgpatt, re.I)
                    for target in modified_targs:
                        if (target == '/' and pkgpatt == '/') or regex_comp.match(target.strip()):
                            watcher_list.append(user)
                            break
                except:
                    print("ERROR: Possibly bad regex for watching user %s: %s" % (user, pkgpatt))
             
        watcher_list = set(watcher_list)
        if len(watcher_list) > 0:
            watcher_text = 'The following users requested to be notified about changes to these packages:\n'
            watcher_text += ', '.join(['@%s' % x for x in watcher_list])
    except Exception as e:
        print(" ERROR: there was a problem while trying to build the watcher list...")
        print("%r" % e)
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
    master_commit_sha = repo.get_branch(branch=pr.base.ref).commit.sha # repo.get_branch("master").commit.sha

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
    print("Merging into: ",pr.base.ref, master_commit_sha)
    print("PR update time", pr.updated_at)
    print("Time UTC:", datetime.utcnow())

    future_commit = False
    future_commit_timedelta_string = None
    if last_commit_date > datetime.utcnow():
        future_td = last_commit_date - datetime.utcnow()
        if future_td.total_seconds() > 120:
            future_commit = True
            future_commit_timedelta_string = str(future_td) + " (hh:mm:ss)"

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
    test_urls = {}
    base_branch_HEAD_changed = False
    master_commit_sha_last_test = None
    stalled_job_info = ''
    legit_tests = set()

    for stat in commit_status:
        name = test_suites.get_test_name(stat.context)
        if name == 'unrecognised':
            continue
        
        if 'buildtest/last' in stat.context:
            name = 'buildtest/last'
            if name in commit_status_time and commit_status_time[name] > stat.updated_at:
                continue
            commit_status_time[name] = stat.updated_at
            # this is the commit SHA in master that we used in the last build test
            master_commit_sha_last_test = stat.description.replace('Last test triggered against ','')
            
            print ("Last build test was run at base sha: %r, current HEAD is %r" % (master_commit_sha_last_test, master_commit_sha))
            
            if not master_commit_sha.strip().startswith(master_commit_sha_last_test.strip()):
                print ("HEAD of base branch is now different to last tested base branch commit")
                base_branch_HEAD_changed = True
            continue

        if name in commit_status_time and commit_status_time[name] > stat.updated_at:
            continue

        commit_status_time[name] = stat.updated_at

        # error, failure, pending, success
        test_statuses[name] = stat.state
        if stat.state in state_labels:
            test_statuses[name] = state_labels[stat.state]
        legit_tests.add(name)
        test_status_exists[name] = True
        if name in test_triggered and test_triggered[name]: # if already True, don't change it
            continue

        test_triggered[name] = ('has been triggered' in stat.description) or (stat.state in ['success', 'failure']) or ('running' in stat.description)

        # some other labels, gleaned from the description (the status API
        # doesn't support these states)
        if ('running' in stat.description):
            test_statuses[name] = 'running'
            test_urls[name] = str(stat.target_url)
        if 'stalled' in stat.description:
            test_statuses[name] = 'stalled'

    if base_branch_HEAD_changed and 'build' in test_statuses and not test_statuses['build'] == 'pending':
        print("The base branch HEAD has changed. We need to reset the status of the build test and notify.")
        test_triggered[name] = False
        test_statuses[name] = 'pending'
        test_status_exists[name] = False
    elif base_branch_HEAD_changed:
        print("The build test status is not present or has already been reset. We will not notify about the changed HEAD.")
        base_branch_HEAD_changed = False

    # check if we've stalled
    tests_ = test_statuses.keys()
    stalled_jobs = []
    for name in tests_:
        if name not in legit_tests:
            continue
        print("Checking if %s has stalled..." % name)
        print("Status is %s" % test_statuses[name])
        if (test_statuses[name] in ['running', 'pending']) and (name in test_triggered) and test_triggered[name]:
            test_runtime = (datetime.utcnow() - commit_status_time[name]).total_seconds()
            print("  Has been running for %d seconds" % test_runtime)
            if test_runtime > test_suites.get_stall_time(name):
                print("  The test has stalled.")
                test_triggered[name] = False # the test may be triggered again.
                test_statuses[name] = 'stalled'
                test_status_exists[name] = False
                stalled_jobs += [name]
                if name in test_urls:
                    stalled_job_info += '\n- %s ([more info](%s))' % (name, test_urls[name])
            else:
                print("  The test has not stalled yet...")
    if 'build' in legit_tests and master_commit_sha_last_test is None:
        if 'build' in test_statuses and test_statuses['build'] != 'pending':
            test_triggered['build'] = False
            test_statuses['build'] = 'pending'
            test_status_exists['build'] = False
            print("There's no record of when we last triggered the build test, and the status is not pending, so we are resetting the status.")

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
    
    bot_comments = []  # keep a track of our comments to avoid duplicate messages and spam.
    
    # now we process comments
    for comment in comments:
        if comment.user.login == repo_config.CMSBUILD_USER:
            bot_comments += [comment.body.strip()]

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
            print ("Triggered! Comment: %r" % comment.body)
            print ('Current test(s): %r' % tests_to_trigger)
            print ('Adding these test(s): %r' % tests )

            for test in tests:
                # check that the test has been triggered on this commit first
                if test in test_triggered and test_triggered[test] and test in test_statuses and not test_statuses[test].strip() in ['failed', 'error']:
                        print ('Current test status: %r' % test_statuses[test])
                        print ("The test has already been triggered for this ref. It will not be triggered again.")
                        tests_already_triggered.append(test)
                        reaction_t = 'confused'
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

    # trigger the 'default' tests if this is the first time we've seen this PR:
    # (but, only if they are in the Mu2e org)
    if trusted_user:
        if not_seen_yet and not dryRun and test_suites.AUTO_TRIGGER_ON_OPEN:
            for test in test_requirements:
                test_statuses[test] = 'pending'
                test_triggered[test] = True
                tests_to_trigger.append(test)
            tests_to_trigger = set(tests_to_trigger)
    
    # now,
    # - trigger tests if indicated (for this specific SHA.)
    # - set the current status for this commit SHA
    # - apply labels according to the state of the latest commit of the PR
    # - make a comment if required
    jobs_have_stalled = False
    for test, state in test_statuses.items():
        if test in legit_tests:
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
                            state="success",
                            target_url="https://github.com/mu2e/Offline",
                            description="Last test triggered against %s" % master_commit_sha[:8],
                            context="mu2e/buildtest/last"
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
        elif state == 'stalled' and not test_status_exists[test]:
            print ("Git status was pending, but the job has stalled.")
            last_commit.create_status(
                            state="error",
                            target_url="https://github.com/mu2e/Offline",
                            description="The job has stalled on Jenkins. It can be re-triggered.",
                            context=test_suites.get_test_alias(test)
                        )
            jobs_have_stalled = True

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
    labelnames =  {x.name for x in issue.labels if 'unrecognised' not in x.name}
    if (labelnames != set(labels)):
        if not dryRun:
            issue.edit(labels=list(labels))
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
    commitlink = git_commit.sha

    if len(tests_to_trigger) > 0:
        if len(tests_already_triggered) > 0:
            already_running_msg = '(already triggered: %s)' % ','.join(tests_already_triggered)

        tests_triggered_msg = TESTS_TRIGGERED_CONFIRMATION.format(
            commit_link=commitlink,
            test_list=', '.join(tests_to_trigger),
            tests_already_running_msg=already_running_msg,
            build_queue_str=get_build_queue_size()
        )


    # decide if we should issue a comment, and what comment to issue
    if not_seen_yet:
        print ("First time seeing this PR - send the user a salutation!")
        if not dryRun:
            post_on_pr(issue, PR_SALUTATION.format(
                pr_author=pr_author,
                changed_folders='\n'.join(['- %s' % s for s in modified_top_level_folders]),
                tests_required=', '.join(test_requirements),
                watchers=watcher_text,
                auth_teams=', '.join(['@Mu2e/%s' % team for team in authed_teams]),
                tests_triggered_msg=tests_triggered_msg,
                non_member_msg='' if trusted_user else PR_AUTHOR_NONMEMBER,
                base_branch=pr.base.ref
            ), bot_comments)

    elif len(tests_to_trigger) > 0:
        # tests were triggered, let people know about it
        if not dryRun:
            post_on_pr(issue, tests_triggered_msg, bot_comments)
            

    elif len(tests_to_trigger) == 0 and len(tests_already_triggered) > 0:
        if not dryRun:
            post_on_pr(issue, TESTS_ALREADY_TRIGGERED.format(
                commit_link=commitlink,
                triggered_tests=', '.join(tests_already_triggered)), bot_comments)
    
    if jobs_have_stalled and not dryRun:
        post_on_pr(
            issue,
            JOB_STALL_MESSAGE.format(joblist=', '.join(stalled_jobs), info=stalled_job_info),
            bot_comments
        )
    if base_branch_HEAD_changed and not dryRun and not len(tests_to_trigger) > 0:
        post_on_pr(issue,
            ":memo: The HEAD of `{base_ref}` has changed to {base_sha}. Tests are now out of date.".format(
                base_ref=pr.base.ref,
                base_sha=master_commit_sha
            ),
            bot_comments
        )
    if 'build' in test_status_exists:
        if future_commit and not test_status_exists['build'] and not dryRun:
            post_on_pr(
                issue,
                f":memo: The latest commit by @{git_commit.committer.name} is timestamped {future_commit_timedelta_string} in the future. Please check that the date and time is set correctly when creating new commits.",
                bot_comments
            )
