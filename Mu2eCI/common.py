import os
import json
from datetime import datetime
from time import sleep, gmtime
from calendar import timegm
from urllib.request import urlopen

from Mu2eCI import config
from Mu2eCI import test_suites
from Mu2eCI.logger import log


def get_build_queue_size():
    jenkins_url = "https://buildmaster.fnal.gov/buildmaster/queue/api/json?pretty=true"

    bqsize = "- API unavailable"

    try:
        contents = json.load(urlopen(jenkins_url))
        nitems = len(contents["items"])
        bqsize = "is empty"
        if nitems > 0:
            bqsize = "has %d jobs" % nitems

    except Exception:
        log.exception("Issues accessing Jenkins Build Queue API")
    return bqsize


# written by CMS-BOT authors
def check_rate_limits(rate_limit, rate_limit_max, rate_limiting_resettime, msg=True):
    doSleep = 0
    rate_reset_sec = rate_limiting_resettime - timegm(gmtime()) + 5
    if msg:
        log.info(
            "API Rate Limit: %s/%s, Reset in %s sec i.e. at %s",
            rate_limit,
            rate_limit_max,
            rate_reset_sec,
            datetime.fromtimestamp(rate_limiting_resettime),
        )
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
    if rate_reset_sec < doSleep:
        doSleep = rate_reset_sec
    if doSleep > 0:
        if msg:
            log.warning(
                "Slowing down for %s sec due to api rate limits %s approching zero"
                % (doSleep, rate_limit)
            )
        sleep(doSleep)
    return


# written by CMS-BOT authors
def api_rate_limits(gh, msg=True):
    gh.get_rate_limit()
    check_rate_limits(
        gh.rate_limiting[0], gh.rate_limiting[1], gh.rate_limiting_resettime, msg
    )


def check_test_cmd_mu2e(full_comment, repository):
    # we have a suite of regex statements to support triggering all kinds of tests.
    # each item in this list matches a trigger statement in a github comment

    # each 'trigger event' function should return:
    # (testnames to run: list, master+branchPR merge result to run them on)

    # tests:
    # desc: code checks -> mu2e/codechecks (context name) -> [jenkins project name]
    # desc: integration build tests -> mu2e/buildtest -> [jenkins project name]
    # desC: physics validation -> mu2e/validation -> [jenkins project name]
    log.debug("Matching regular expressions to this comment.")
    try:
        log.debug(repr(full_comment))
    except Exception:
        log.exception("could not print comment...")

    for regex, handler in test_suites.TESTS:
        # returns the first match in the comment
        match = regex.search(full_comment)
        if match is None:
            log.debug("NOT MATCHED - %s", str(regex.pattern))
            continue
        handle = handler(match)

        if handle is None:
            log.debug("MATCHED - BUT NoneType HANDLE RETURNED - %s", str(regex.pattern))
            continue
        log.debug("MATCHED - %s", str(regex.pattern))
        return handle, True

    if test_suites.regex_mentioned.search(full_comment) is not None:
        log.debug("MATCHED - but unrecognised command")
        return None, True
    log.debug("NO MATCHES")

    return None, False


def create_properties_file_for_test(
    test,
    repository,
    pr_number,
    pr_commit_sha,
    master_commit_sha,
    extra_env,
    dryRun=False,
):
    parameters = {**extra_env}

    repo_partsX = repository.replace("/", "-")  # mu2e/Offline ---> mu2e-Offline
    out_file_name = "trigger-mu2e-%s-%s-%s.properties" % (
        test.replace(" ", "-"),
        repo_partsX,
        pr_number,
    )

    parameters["TEST_NAME"] = test
    parameters["REPOSITORY"] = repository
    parameters["PULL_REQUEST"] = pr_number
    parameters["COMMIT_SHA"] = pr_commit_sha
    parameters["MASTER_COMMIT_SHA"] = master_commit_sha

    if dryRun:
        log.info("Not creating cleanup properties file (dry-run): %s", out_file_name)
        return
    log.info("Creating properties file %s", out_file_name)

    with open(out_file_name, "w") as out_file:
        for k in parameters:
            out_file.write("%s=%s\n" % (k, parameters[k]))


def get_modified(modified_files):
    modified_top_level_folders = []
    for f in modified_files:
        filename, file_extension = os.path.splitext(f.filename)
        log.debug("Changed file (%s): %s%s", file_extension, filename, file_extension)

        splits = filename.split("/")
        if len(splits) > 1:
            modified_top_level_folders.append(splits[0])
        else:
            modified_top_level_folders.append("/")

    return set(modified_top_level_folders)


def get_authorised_users(mu2eorg, repo, branch="all"):
    yaml_contents = config.auth_teams
    authed_users = []
    authed_teams = yaml_contents["all"]
    if branch in yaml_contents:
        authed_teams += yaml_contents[branch]

    authed_teams = set(authed_teams)
    log.info("Authorised Teams: %s", ", ".join(authed_teams))

    for team_slug in authed_teams:
        teamobj = mu2eorg.get_team_by_slug(team_slug)
        authed_users += [mem.login for mem in teamobj.get_members()]

    # users authorised to communicate with this bot
    return set(authed_users), authed_teams


def post_on_pr(issue, comment, previous_bot_comments):
    if comment in previous_bot_comments:
        log.warning(
            "SPAM PROTECTION - We are posting something we already "
            "posted before! Something is wrong!"
        )
        return
    issue.create_comment(comment)
