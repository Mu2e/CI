from github import Github

def comment_gh_pr(gh, repo, pr, msg):
    repo = gh.get_repo(repo)
    pr   = repo.get_issue(pr)

    # This script provides the mechanism that reports on
    # job statuses.
    # the message is read from a 'report file' supplied by the Jenkins job.

    # The format should be:
    # line 1: SHA of the tested commit
    # line 2: the job 'context' or the string-identifier for the job
    # line 3: job status: success/failure/error/pending
    # line 4: a one-line description of the state
    # line 5: Link to detailed results/information
    # line 6+: The comment to post on the Pull Request, or, if no comment desired, add 'NOCOMMENT'

    lines = msg.split('\n')
    if len(lines) < 6: # need at least six lines.
        # Post instead the msg, and skip the git status.
        pr.create_comment("Error: A Jenkins job did not report output in the correct format. The output was as follows:\n%s" % msg)
        return

    test_commit_sha = lines[0]
    context = lines[1]
    state = lines[2]
    desc = lines[3]
    details_link = lines[4]

    repo.get_commit(sha=test_commit_sha).create_status(
        state=state,
        target_url=details_link,
        description=desc,
        context=context
    )


    comment_msg = '\n'.join(lines[5:])
    # some status updates by commenting might not be necessary.
    if not 'NOCOMMENT' in comment_msg:
        pr.create_comment(comment_msg)
