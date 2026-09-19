# Release checklist

First release of `clipper2-py` to PyPI. Publishing is done by
[.github/workflows/wheels.yml](.github/workflows/wheels.yml) through PyPI Trusted
Publishing: no API token exists and none is needed, but the project has to be claimed on
PyPI first, and that part only the owner can do.

## 1. Owner: create the pending Trusted Publisher on PyPI

`clipper2-py` does not exist on PyPI yet, so the publisher is registered *before* the
project, as a "pending" one. Sign in to PyPI, open
<https://pypi.org/manage/account/publishing/>, and under **Add a new pending publisher**
pick the GitHub tab and fill in exactly:

| Field | Value |
| --- | --- |
| PyPI Project Name | `clipper2-py` |
| Owner | `Maksim-Burtsev` |
| Repository name | `clipper2-py` |
| Workflow name | `wheels.yml` |
| Environment name | `pypi` |

The first successful publish turns the pending publisher into a normal one and creates
the project.

## 2. Owner: create the `pypi` environment on GitHub

The publishing job declares `environment: pypi`, and the environment name is part of what
PyPI verifies, so it has to exist with that exact spelling.

<https://github.com/Maksim-Burtsev/clipper2-py/settings/environments> → **New
environment** → name `pypi` → Configure environment. No secrets and no variables are
needed; Trusted Publishing uses the OIDC token, which the job requests with
`permissions: id-token: write`.

Optional, and the point of using an environment at all: add **Required reviewers**
(yourself) so that every publish waits for a manual approval, and restrict the
environment's deployment branches to tags.

The same job also creates the GitHub release with `contents: write` and the built-in
`GITHUB_TOKEN`. If the repository's **Settings → Actions → General → Workflow
permissions** is set to "Read repository contents and packages permissions", that is
fine — the job asks for the write scope itself — but an organisation policy that forbids
elevating it would break the release step.

## 3. Before tagging: verification

- [ ] `main` is green: the `wheels` workflow has passed on the commit to be tagged, with
      all five wheel jobs (ubuntu-24.04 x86_64, ubuntu-24.04-arm aarch64, macos-14 arm64,
      macos-14 x86_64, windows-2022 AMD64), the `sdist` job and the `numpy-floor` job.
      Wheels are built for CPython 3.10–3.14; every job runs `pytest {project}/tests`
      inside the wheel, except macOS x86_64, which cannot run on an arm64 runner.
- [ ] `version` in `pyproject.toml` is the version to release. The workflow's first step
      compares it with the tag and fails the build if they differ.
- [ ] `CHANGELOG.md` has the entry for that version, with the release date instead of
      "unreleased".
- [ ] The bundled upstream is the intended one: `clipper2.CLIPPER2_VERSION` and the
      `third_party/Clipper2` submodule commit (tag `Clipper2_2.0.1`).
- [ ] The full test suite passes locally, including the differential tests against the
      C++ reference binary:

      cmake -S tests/reference -B build/ref -DCMAKE_BUILD_TYPE=Release
      cmake --build build/ref
      pytest tests

- [ ] The sdist builds and is valid:

      pipx run --spec build pyproject-build --sdist
      pipx run twine check dist/*

- [ ] The sdist installs from scratch and its tests pass (this is also what the `sdist`
      job does in CI, on Linux):

      python -m venv /tmp/sdist-venv
      /tmp/sdist-venv/bin/pip install dist/clipper2_py-*.tar.gz pytest
      /tmp/sdist-venv/bin/python -m pytest tests

- [ ] `README.md` renders on the PyPI page (`twine check` covers this) and its links
      point at files that exist in the sdist.

## 4. Tag and push

The tag is the trigger; nothing else has to be done by hand.

    git tag -a v0.1.0 -m "clipper2-py 0.1.0"
    git push origin v0.1.0

The workflow then, on that tag:

1. checks that the tag matches `version` in `pyproject.toml` (`v0.1.0` ↔ `0.1.0`);
2. builds the wheels on the five platforms and the sdist, and runs the test suites;
3. in the `publish` job — which needs all three of `build`, `sdist` and `numpy-floor`, and
   runs only for `refs/tags/v*` — downloads every `wheels-*` artifact into `dist/`
   (the sdist artifact is named `wheels-sdist`, so it is published too) and uploads them
   with `pypa/gh-action-pypi-publish` and `skip-existing: true`;
4. creates the GitHub release for the tag with `gh release create <tag> dist/*
   --generate-notes`, falling back to `gh release upload --clobber` if the release
   already exists.

If the `pypi` environment has required reviewers, the `publish` job waits for approval
before any of this.

## 5. After the release

- [ ] <https://pypi.org/project/clipper2-py/> exists, shows the README, and lists the
      wheels for all five platforms plus the sdist.
- [ ] The pending publisher on PyPI is now a normal publisher of the project.
- [ ] `pip install clipper2-py` works in a clean virtualenv and
      `python -c "import clipper2; print(clipper2.__version__, clipper2.CLIPPER2_VERSION)"`
      prints the expected pair.
- [ ] The GitHub release for the tag exists with the files attached.
- [ ] The PyPI and Python-versions badges in `README.md` resolve (they are dead until the
      first release).
- [ ] Bump `version` in `pyproject.toml` to the next development version and open a new
      "unreleased" section in `CHANGELOG.md`.
