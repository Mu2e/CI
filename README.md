# CI

![CI test status](https://github.com/Mu2e/CI/actions/workflows/tests.yml/badge.svg)

A GitHub bot (@FNALbuild) which handles continuous integration and tests for Mu2e/Offline. Inspired by CMS-BOT.

Thanks to Patrick Gartung (maintains Web Hook interface to FNAL Jenkins) and the authors of CMS-BOT.


## pre-commit hooks

To pass CI in this repository you will need `pre-commit`.
```
pip install pre-commit
```

To install commit hooks,
```
pre-commit install
```

To just run and apply fixes,
```
pre-commit run --all
```
