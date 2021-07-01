import re
from datetime import datetime
from socket import setdefaulttimeout

from Mu2eCI import config
from Mu2eCI import test_suites
from Mu2eCI.logger import log
from Mu2eCI.common import (
    api_rate_limits,
    post_on_pr,
    get_modified,
    get_authorised_users,
    check_test_cmd_mu2e,
    create_properties_file_for_test,
    get_build_queue_size,
)
from Mu2eCI.messages import (
    PR_SALUTATION,
    PR_AUTHOR_NONMEMBER,
    TESTS_ALREADY_TRIGGERED,
    TESTS_TRIGGERED_CONFIRMATION,
    JOB_STALL_MESSAGE,
    BASE_BRANCH_HEAD_CHANGED,
)

setdefaulttimeout(300)


def process_pr(gh, repo, issue, dryRun=False, child_call=0):
    if child_call > 2:
        log.warning("Stopping recursion")
        return
    api_rate_limits(gh)

    if not issue.pull_request:
        log.warning("Ignoring: Not a PR")
        return

    prId = issue.number
    pr = repo.get_pull(prId)

    if pr.changed_files == 0:
        log.warning("Ignoring: PR with no files changed")
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
            log.info(
                "Triggering check on all other open PRs as "
                "this PR was merged within the last 2 minutes."
            )
            pulls_to_check = repo.get_pulls(state="open", base=pr.base.ref)
            for pr_ in pulls_to_check:
                process_pr(
                    gh,
                    repo,
                    pr_.as_issue(),
                    dryRun,
                    child_call=child_call + 1,
                )

    if pr.state == "closed":
        log.info("Ignoring: PR in closed state")
        return

    mu2eorg = gh.get_organization("Mu2e")
    trusted_user = mu2eorg.has_in_members(issue.user)

    authorised_users, authed_teams = get_authorised_users(
        mu2eorg, repo, branch=pr.base.ref
    )

    # allow the PR author to execute CI actions:
    if trusted_user:
        authorised_users.add(issue.user.login)

    log.debug("Authorised Users: %s", ", ".join(authorised_users))

    not_seen_yet = True
    last_time_seen = None
    labels = set()

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
    log.debug("Build Targets changed:")
    log.debug("\n".join(["- %s" % s for s in modified_top_level_folders]))

    watchers = config.watchers

    # Figure out who is watching the modified packages and notify them
    log.debug("watchers: %s", ", ".join(watchers))
    watcher_text = ""
    watcher_list = []
    try:
        modified_targs = [x.lower() for x in modified_top_level_folders]
        for user, packages in watchers.items():
            for pkgpatt in packages:
                try:
                    regex_comp = re.compile(pkgpatt, re.I)
                    for target in modified_targs:
                        if (target == "/" and pkgpatt == "/") or regex_comp.match(
                            target.strip()
                        ):
                            watcher_list.append(user)
                            break
                except Exception:
                    log.warning(
                        "ERROR: Possibly bad regex for watching user %s: %s"
                        % (user, pkgpatt)
                    )

        watcher_list = set(watcher_list)
        if len(watcher_list) > 0:
            watcher_text = (
                "The following users requested to be notified about "
                "changes to these packages:\n"
            )
            watcher_text += ", ".join(["@%s" % x for x in watcher_list])
    except Exception:
        log.exception("There was a problem while trying to build the watcher list...")

    # get required tests
    test_requirements = test_suites.get_tests_for(modified_top_level_folders)
    log.info("Tests required: %s", ", ".join(test_requirements))

    # set their status to 'pending' (will be updated shortly after)
    for test in test_requirements:
        test_statuses[test] = "pending"
        test_triggered[test] = False
        test_status_exists[test] = False

    # this will be the commit of master that the PR is merged
    # into for the CI tests (for a build test this is just the current HEAD.)
    master_commit_sha = repo.get_branch(
        branch=pr.base.ref
    ).commit.sha  # repo.get_branch("master").commit.sha

    # get latest commit
    last_commit = pr.get_commits().reversed[0]
    git_commit = last_commit.commit
    if git_commit is None:
        return

    last_commit_date = git_commit.committer.date
    log.debug(
        "Latest commit by %s at %r",
        git_commit.committer.name,
        last_commit_date,
    )

    log.info("Latest commit message: %s", git_commit.message.encode("ascii", "ignore"))
    log.info("Latest commit sha: %s", git_commit.sha)
    log.info("Merging into: %s %s", pr.base.ref, master_commit_sha)
    log.info("PR update time %s", pr.updated_at)
    log.info("Time UTC: %s", datetime.utcnow())

    future_commit = False
    future_commit_timedelta_string = None
    if last_commit_date > datetime.utcnow():
        future_td = last_commit_date - datetime.utcnow()
        if future_td.total_seconds() > 120:
            future_commit = True
            future_commit_timedelta_string = str(future_td) + " (hh:mm:ss)"
            log.warning("This commit is in the future! That is weird!")

    # now get commit statuses
    # this is how we figure out the current state of tests
    # on the latest commit of the PR.
    commit_status = last_commit.get_statuses()

    # we can translate git commit status API 'state' strings if needed.
    state_labels = config.main["labels"]["states"]

    state_labels_colors = config.main["labels"]["colors"]

    commit_status_time = {}
    test_urls = {}
    base_branch_HEAD_changed = False
    master_commit_sha_last_test = None
    stalled_job_info = ""
    legit_tests = set()

    for stat in commit_status:
        name = test_suites.get_test_name(stat.context)
        log.debug(f"Processing commit status: {stat.context}")
        if "buildtest/last" in stat.context:
            log.debug("Check if this is when we last triggered the test.")
            name = "buildtest/last"
            if (
                name in commit_status_time
                and commit_status_time[name] > stat.updated_at
            ):
                continue
            commit_status_time[name] = stat.updated_at
            # this is the commit SHA in master that we used in the last build test
            master_commit_sha_last_test = stat.description.replace(
                "Last test triggered against ", ""
            )

            log.info(
                "Last build test was run at base sha: %r, current HEAD is %r"
                % (master_commit_sha_last_test, master_commit_sha)
            )

            if not master_commit_sha.strip().startswith(
                master_commit_sha_last_test.strip()
            ):
                log.info(
                    "HEAD of base branch is now different to last tested base branch commit"
                )
                base_branch_HEAD_changed = True
            else:
                log.info("HEAD of base branch is a match.")
            continue
        if name == "unrecognised":
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
        if (
            name in test_triggered and test_triggered[name]
        ):  # if already True, don't change it
            continue

        test_triggered[name] = (
            ("has been triggered" in stat.description)
            or (stat.state in ["success", "failure"])
            or ("running" in stat.description)
        )

        # some other labels, gleaned from the description (the status API
        # doesn't support these states)
        if "running" in stat.description:
            test_statuses[name] = "running"
            test_urls[name] = str(stat.target_url)
        if "stalled" in stat.description:
            test_statuses[name] = "stalled"

    if (
        (master_commit_sha_last_test is None or base_branch_HEAD_changed)
        and "build" in test_statuses
        and not test_statuses["build"] == "pending"
    ):
        log.info(
            "The base branch HEAD has changed or we didn't know the base branch of the last test."
            " We need to reset the status of the build test and notify."
        )
        test_triggered["build"] = False
        test_statuses["build"] = "pending"
        test_status_exists["build"] = False
    elif base_branch_HEAD_changed:
        log.info(
            "The build test status is not present or has already been reset. "
            "We will not notify about the changed HEAD."
        )
        base_branch_HEAD_changed = False

    # check if we've stalled
    tests_ = test_statuses.keys()
    stalled_jobs = []
    for name in tests_:
        if name not in legit_tests:
            continue
        log.info("Checking if %s has stalled...", name)
        log.info("Status is %s", test_statuses[name])
        if (
            (test_statuses[name] in ["running", "pending"])
            and (name in test_triggered)
            and test_triggered[name]
        ):
            test_runtime = (
                datetime.utcnow() - commit_status_time[name]
            ).total_seconds()
            log.info("  Has been running for %d seconds", test_runtime)
            if test_runtime > test_suites.get_stall_time(name):
                log.info("  The test has stalled.")
                test_triggered[name] = False  # the test may be triggered again.
                test_statuses[name] = "stalled"
                test_status_exists[name] = False
                stalled_jobs += [name]
                if name in test_urls:
                    stalled_job_info += "\n- %s ([more info](%s))" % (
                        name,
                        test_urls[name],
                    )
            else:
                log.info("  The test has not stalled yet...")
    if "build" in legit_tests and master_commit_sha_last_test is None:
        if "build" in test_statuses and test_statuses["build"] in [
            "success",
            "error",
            "failure",
        ]:
            test_triggered["build"] = False
            test_statuses["build"] = "pending"
            test_status_exists["build"] = False
            log.info(
                "There's no record of when we last triggered the build test, "
                "and the status is not pending, so we are resetting the status."
            )

    # now process PR comments that come after when
    # the bot last did something, first figuring out when the bot last commented
    pr_author = issue.user.login
    comments = issue.get_comments()
    for comment in comments:
        # loop through once to ascertain when the bot last commented
        if comment.user.login == config.main["bot"]["username"]:
            if last_time_seen is None or last_time_seen < comment.created_at:
                not_seen_yet = False
                last_time_seen = comment.created_at
                log.debug(
                    "Bot user comment found: %s, %s",
                    comment.user.login,
                    str(last_time_seen),
                )
    log.info("Last time seen %s", str(last_time_seen))

    bot_comments = (
        []
    )  # keep a track of our comments to avoid duplicate messages and spam.

    # now we process comments
    for comment in comments:
        if comment.user.login == config.main["bot"]["username"]:
            bot_comments += [comment.body.strip()]

        # Ignore all messages which are before last commit.
        if comment.created_at < last_commit_date:
            log.debug("IGNORE COMMENT (before last commit)")
            continue

        # neglect comments we've already responded to
        if last_time_seen is not None and (comment.created_at < last_time_seen):
            log.debug(
                "IGNORE COMMENT (seen) %s %s < %s",
                comment.user.login,
                str(comment.created_at),
                str(last_time_seen),
            )
            continue

        # neglect comments by un-authorised users
        if (
            comment.user.login not in authorised_users
            or comment.user.login == config.main["bot"]["username"]
        ):
            log.debug(
                "IGNORE COMMENT (unauthorised, or bot user) - %s", comment.user.login
            )
            continue

        for react in comment.get_reactions():
            if react.user.login == config.main["bot"]["username"]:
                log.debug(
                    "IGNORE COMMENT (we've seen it and reacted to say we've seen it) - %s",
                    comment.user.login,
                )

        reaction_t = None
        trigger_search, mentioned, extra_env = None, None, None
        # now look for bot triggers
        # check if the comment has triggered a test
        try:
            trigger_search, mentioned, extra_env = check_test_cmd_mu2e(
                comment.body, repo.full_name
            )
        except ValueError:
            log.exception("Failed to trigger a test due to invalid inputs")
            reaction_t = "-1"
        except Exception:
            log.exception("Failed to trigger a test.")

        tests_already_triggered = []

        if trigger_search is not None:
            tests, _ = trigger_search
            log.info("Test trigger found!")
            log.debug("Comment: %r", comment.body)
            log.info("Current test(s): %r" % tests_to_trigger)
            log.info("Adding these test(s): %r" % tests)

            for test in tests:
                # check that the test has been triggered on this commit first
                if (
                    test in test_triggered
                    and test_triggered[test]
                    and test in test_statuses
                    and not test_statuses[test].strip() in ["failed", "error"]
                ):
                    log.debug("Current test status: %s", test_statuses[test])
                    log.info(
                        "The test has already been triggered for this ref. "
                        "It will not be triggered again."
                    )
                    tests_already_triggered.append(test)
                    reaction_t = "confused"
                    continue
                else:
                    test_triggered[test] = False

                if not test_triggered[test]:  # is the test already running?
                    # ok - now we can trigger the test
                    log.info(
                        "The test has not been triggered yet. It will now be triggered."
                    )

                    # update the 'state' of this commit
                    test_statuses[test] = "pending"
                    test_triggered[test] = True

                    # add the test to the queue of tests to trigger
                    tests_to_trigger.append((test, extra_env))
                    reaction_t = "+1"
        elif mentioned:
            # we didn't recognise any commands!
            reaction_t = "confused"

        if reaction_t is not None:
            # "React" to the comment to let the user know we have acknowledged their comment!
            comment.create_reaction(reaction_t)

    # trigger the 'default' tests if this is the first time we've seen this PR:
    # (but, only if they are in the Mu2e org)
    if trusted_user:
        if not_seen_yet and not dryRun and test_suites.AUTO_TRIGGER_ON_OPEN:
            for test in test_requirements:
                test_statuses[test] = "pending"
                test_triggered[test] = True
                if test not in [t[0] for t in tests_to_trigger]:
                    tests_to_trigger.append((test, {}))

    # now,
    # - trigger tests if indicated (for this specific SHA.)
    # - set the current status for this commit SHA
    # - apply labels according to the state of the latest commit of the PR
    # - make a comment if required
    jobs_have_stalled = False

    triggered_tests, extra_envs = list(zip(*tests_to_trigger))
    for test, state in test_statuses.items():
        if test in legit_tests:
            labels.add(f"{test} {state}")

        if test in triggered_tests:
            log.info("Test will now be triggered! %s", test)
            # trigger the test in jenkins
            create_properties_file_for_test(
                test,
                repo.full_name,
                prId,
                git_commit.sha,
                master_commit_sha,
                extra_envs[triggered_tests.index(test)],
            )
            if not dryRun:
                if test == "build":
                    # we need to store somewhere the master commit SHA
                    # that we merge into for the build test (for validation)
                    # this is overlapped with the next, more human readable message
                    last_commit.create_status(
                        state="success",
                        target_url="https://github.com/mu2e/Offline",
                        description="Last test triggered against %s"
                        % master_commit_sha[:8],
                        context="mu2e/buildtest/last",
                    )

                last_commit.create_status(
                    state="pending",
                    target_url="https://github.com/mu2e/Offline",
                    description="The test has been triggered in Jenkins",
                    context=test_suites.get_test_alias(test),
                )
            log.info(
                "Git status created for SHA %s test %s - since the test has been triggered.",
                git_commit.sha,
                test,
            )
        elif state == "pending" and test_status_exists[test]:
            log.info(
                "Git status unchanged for SHA %s test %s - the existing one is up-to-date.",
                git_commit.sha,
                test,
            )
        elif state == "stalled" and not test_status_exists[test]:
            log.info("Git status was pending, but the job has stalled.")
            last_commit.create_status(
                state="error",
                target_url="https://github.com/mu2e/Offline",
                description="The job has stalled on Jenkins. It can be re-triggered.",
                context=test_suites.get_test_alias(test),
            )
            jobs_have_stalled = True

        elif (
            state == "pending"
            and not test_triggered[test]
            and not test_status_exists[test]
        ):
            log.debug(test_status_exists)
            log.info(
                "Git status created for SHA %s test %s - since there wasn't one already."
                % (git_commit.sha, test)
            )
            labels.add(f"{test} {state}")
            # indicate that the test is pending but
            # we're still waiting for someone to trigger the test
            if not dryRun:
                last_commit.create_status(
                    state="pending",
                    target_url="https://github.com/mu2e/Offline",
                    description="This test has not been triggered yet.",
                    context=test_suites.get_test_alias(test),
                )
        # don't do anything else with commit statuses
        # the script handler that handles Jenkins job results will update the commits accordingly

    # check if labels have changed
    labelnames = {x.name for x in issue.labels if "unrecognised" not in x.name}
    if labelnames != labels:
        if not dryRun:
            issue.edit(labels=list(labels))
        log.debug("Labels have changed to: %s", ", ".join(labels))

    # check label colours
    try:
        for label in issue.labels:
            if label.color == "ededed":
                # the label color isn't set
                for labelcontent, col in state_labels_colors.items():
                    if labelcontent in label.name:
                        label.edit(label.name, col)
                        break
    except Exception:
        log.exception("Failed to set label colours!")

    # construct a reply if tests have been triggered.
    tests_triggered_msg = ""
    already_running_msg = ""
    commitlink = git_commit.sha

    if len(tests_to_trigger) > 0:
        if len(tests_already_triggered) > 0:
            already_running_msg = "(already triggered: %s)" % ",".join(
                tests_already_triggered
            )

        tests_triggered_msg = TESTS_TRIGGERED_CONFIRMATION.format(
            commit_link=commitlink,
            test_list=", ".join(list(zip(*tests_to_trigger))[0]),
            tests_already_running_msg=already_running_msg,
            build_queue_str=get_build_queue_size(),
        )

    # decide if we should issue a comment, and what comment to issue
    if not_seen_yet:
        log.info("First time seeing this PR - send the user a salutation!")
        if not dryRun:
            post_on_pr(
                issue,
                PR_SALUTATION.format(
                    pr_author=pr_author,
                    changed_folders="\n".join(
                        ["- %s" % s for s in modified_top_level_folders]
                    ),
                    tests_required=", ".join(test_requirements),
                    watchers=watcher_text,
                    auth_teams=", ".join(["@Mu2e/%s" % team for team in authed_teams]),
                    tests_triggered_msg=tests_triggered_msg,
                    non_member_msg="" if trusted_user else PR_AUTHOR_NONMEMBER,
                    base_branch=pr.base.ref,
                ),
                bot_comments,
            )

    elif len(tests_to_trigger) > 0:
        # tests were triggered, let people know about it
        if not dryRun:
            post_on_pr(issue, tests_triggered_msg, bot_comments)

    elif len(tests_to_trigger) == 0 and len(tests_already_triggered) > 0:
        if not dryRun:
            post_on_pr(
                issue,
                TESTS_ALREADY_TRIGGERED.format(
                    commit_link=commitlink,
                    triggered_tests=", ".join(tests_already_triggered),
                ),
                bot_comments,
            )

    if jobs_have_stalled and not dryRun:
        post_on_pr(
            issue,
            JOB_STALL_MESSAGE.format(
                joblist=", ".join(stalled_jobs), info=stalled_job_info
            ),
            bot_comments,
        )
    if base_branch_HEAD_changed and not dryRun and not len(tests_to_trigger) > 0:
        post_on_pr(
            issue,
            BASE_BRANCH_HEAD_CHANGED.format(
                base_ref=pr.base.ref, base_sha=master_commit_sha
            ),
            bot_comments,
        )
    if "build" in test_status_exists:
        if future_commit and not test_status_exists["build"] and not dryRun:
            post_on_pr(
                issue,
                f":memo: The latest commit by @{git_commit.committer.name} is "
                f"timestamped {future_commit_timedelta_string} in the future. "
                "Please check that the date and time is set correctly when creating new commits.",
                bot_comments,
            )
