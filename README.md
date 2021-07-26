# Mu2e/CI

![CI test status](https://github.com/Mu2e/CI/actions/workflows/tests.yml/badge.svg) [![pre-commit.ci status](https://results.pre-commit.ci/badge/github/Mu2e/CI/master.svg)](https://results.pre-commit.ci/latest/github/Mu2e/CI/master)

A GitHub bot (@FNALbuild) which handles continuous integration and testing workflows for the [Mu2e](https://github.com/Mu2e) Offline software. It is inspired by [CMS-BOT](https://github.com/cms-sw/cms-bot).

Thanks to Patrick Gartung (@gartung), and the authors of [CMS-BOT](https://github.com/cms-sw/cms-bot).

## Development
### pre-commit
This repository uses `pre-commit` and `pre-commit.ci` to enforce code style and fix problems. `pre-commit.ci` will push fixes automatically to branches and pull requests.

#### Running a check locally

You will need `pre-commit`.
```
pip install pre-commit
```

To install commit hooks,
```
pre-commit install
```
`pre-commit` will check everything before a `git commit` operation.

To run and apply fixes,
```
pre-commit run --all
```
