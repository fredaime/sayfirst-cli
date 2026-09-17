<!-- SPDX-License-Identifier: Apache-2.0 -->
# Publication checklist

One page, for the person who publishes. Nothing here is done by a workflow: each line is an act
the operator takes, and every one of them leads to the same act at the end — the tag, the last
line of the list below. Cutting it is the only thing that publishes anything: the release
workflow starts on no other event, and a run of it started by hand publishes nothing. Everything
above that line is what has to be true before it is cut.

Every open repository of the project carries this list, in this order, with the lines that can
only be true of one repository written for that repository. Tick a line when its act is done,
with the date and the reference the act produced, so that this page records what was performed
rather than what was intended. `tests/test_publication_checklist_names_every_act.py` fails when
an act the constitution names is not a line here; whether a ticked line is true is held by
review, because no file can read a filing at a registry, an answer from counsel, or a setting of
the hosting platform.

## Before the tag

- [ ] **File the marks for the name, and read the filing back against every name this project will
  publish.** Nothing is published under the name until they are filed — no package on an index,
  no public repository, no announcement (article 0). The marks are filed for the name itself, the
  one every published distribution carries as the whole of its name or as its prefix. What is read
  back against the filing is, first, three public repository names —
  `sayfirst-control-plane`, `sayfirst-cli` and `sayfirst-governed-agent-demo` — and then, for each
  repository in turn, the distribution names its own project files declare, which is where they
  are spelled and where a name guard of its own holds the spelling. The demonstrator publishes no
  distribution in the first release, so for that repository the name to read back is the
  repository's. Reading the project files rather than a list copied here is the point: a list here
  would be a second spelling, and a second spelling drifts. A name the filing refuses is changed
  in the guards that hold it — `tests/test_pointers_survive_publication.py` among them — and in
  every project file, before anything is published under any of them. Record the filing's date and
  its reference on this line.
- [ ] **Obtain counsel's confirmation of the reliance on the exemption for publicly available
  software**, for the cryptography this project embeds, under the dual-use regulation and under
  the regime of any jurisdiction whose index the project publishes through (article 15). It is
  wanted before the first public release. Record the date the answer was given and the reference
  it can be found under; the answer itself stays with the operator, and no file here holds it.
- [ ] **Obtain counsel's confirmation of the sign-off's effect as a licence grant** — the Developer
  Certificate of Origin's effect under the law that applies to the lead (article 15) — before the
  same release. Record the date and the reference the same way. Neither answer is a thing any
  check in these repositories can read, which is why each is a line rather than a test.
- [ ] Confirm or rename the public repository before the tag. Every URL this distribution
  publishes begins with `https://github.com/fredaime/sayfirst-cli`, and the guard
  `tests/test_pointers_survive_publication.py` holds that name. A different name is a change to
  both, in one commit, before the tag is cut.
- [ ] Make the two workflow edits publication requires, and read what the two files claim about
  article 16 again afterwards. `ci.yml` builds the contract from a checkout of the control plane's
  repository, which this project has not opened yet, and carries `CONTROL_PLANE_READ_TOKEN` to
  reach it: on publication day that checkout becomes one of the public repository with no token,
  or an ordinary install of the published contract. `release.yml`'s second checkout becomes an
  install of the published distributions at the version this client pins. Both files say
  publication day is also the day article 16's « a fork can build, test and contribute with
  nothing but this repository » is met — which is true only once these two edits land. Until they
  do, a fork still gets a reduced gate on a day two published files say otherwise. They are edits
  to the tree, so they land before the tree is reviewed and pushed.
- [ ] Create the public repository, fresh, with private vulnerability reporting enabled in the
  same act (article 0), so that `SECURITY.md` names a channel that exists from the first public
  minute — the hosting platform allows that setting on a public repository only. Every open
  repository of the project is published the same way, this one included: a new repository whose
  first commit is the reviewed tree, with no history, no branch, no tag, no issue and no pull
  request carried across. This repository's own visibility is never changed, and it is kept
  afterwards as the record of how the open one was built. Review the tree and run the whole gate
  over exactly what will be pushed, before the push, so that every claim the guards hold is
  checked rather than asserted. Let the private address in `SECURITY.md` leave in the same change.
- [ ] **Change the display name before the tag if wanted.** The author recorded in this
  repository's one project file is `fredaime <frederic.aime@gmail.com>`, which is the identity
  every commit is signed off under. A different display name for the index is a change to that
  file's `authors` table, before the tag.
- [ ] **Require a reviewer on the `pypi` deployment environment, and create the trusted-publishing
  relationship** for this repository's release workflow on the index itself. The release workflow
  names the environment and asks for `id-token: write` instead of a stored token; whether the
  environment demands an approval, and whether the index trusts this workflow's identity, are
  settings of the repository and of the index that no file here can read, and none of them claims
  to.
- [ ] **Set the sign-off check as a required status** in the public repository's branch protection.
  Contributions arrive under the Developer Certificate of Origin (article 15), and whether a
  failing check blocks a merge is a branch-protection setting of the public repository which no
  check in this tree can read (article 16). Two acts in one order: the repository's own gate runs
  the check on every pull request, and the setting makes a failure block. It is a line here
  because an act held by review with no line is an act nobody is reminded to perform.
- [ ] The concept count of article 18 is published by the control plane and not here. Nothing on
  this list asks for it, and no document of this repository carries it; the line exists so that a
  reader of this page knows where the count lives rather than going to look for a page this
  repository does not keep.
- [ ] Prove the dry run before the tag. This workflow's gate step reaches the control plane at its
  own public repository, which does not exist until the marks are filed and it is published — so
  a dispatch cannot finish in CI before then. The dry run is proven locally by hand instead, on
  the release branch, recorded below under "What the dry run proved, and when". After
  publication, dispatch the release workflow in CI the same way, with `publish` left `false`, and
  read what it built from the run's summary.
- [ ] **Cut the tag on a commit whose whole gate is green on the default branch.** A tag reproduces
  one leg of the gate and no more, while the other legs run on pushes to the default branch and
  on pull requests — `.github/workflows/ci.yml` says which runs where — so the last place every
  leg was held for that tree is its run on the default branch together with the pull request that
  merged it. A tag cut anywhere else is a release that nothing checked whole.

## The order across the three repositories

The three open repositories are published in one order, and each step needs the one before it.

1. **The control plane**, and its distributions on the index. Everything downstream reads the
   index entry, not the repository alone.
2. **The client**, after the two workflow edits publication requires have landed in it. Its
   release workflow reads the control plane's public repository at the tag its own pins name,
   which resolves only after step 1, and the checkout its gate makes of a sibling that is not
   published becomes an ordinary install — which is the day article 16's promise about a fork
   becomes true.
3. **The demonstrator**, `sayfirst-governed-agent-demo`, last: it installs the client from the
   index and pins the control plane's distributions, so it needs both. It is published as a fresh
   repository at the release tag, from its own publication checklist, and it uploads no
   distribution to any index in the first release — its last act is the repository and a tag.

## What the dry run proved, and when

Run by hand on the release branch, in the order the release workflow runs them: the version
reader with `--expect`, the full gate, `uv build`, and `uvx twine@7.0.0 check`. Nothing was
published: the publish job runs for a tag and there was none. Recorded 2026-09-16.

The ref the gate read is part of what was proven, so it is named rather than summarised: a local
checkout of the control plane, at its own release branch, which holds the content that
repository's `0.2.0` tag will name once it is published. The tag does not exist yet, and neither
does the public repository the release workflow reads it from.

- the distribution answered one version, `0.2.0`: `sayfirst-cli`;
- the gate was **full green**, not reduced — a release is never cut from a reduced gate, and the
  workflow refuses a reduced one by name;
- two artefacts were built, a wheel and a source distribution, both carrying `0.2.0`;
- `twine check` verdict: PASSED, on both;
- the built wheel declares its licence as `License-Expression`, and carries no licence classifier
  beside it. An index refuses a distribution that carries both, and `twine check` does not catch
  it, so it was read out of the built metadata instead.

What this does **not** prove, and no dry run can. The one step of the release path that nothing
has exercised is the second checkout itself: the PUBLIC control-plane repository, at the tag this
client's own pin names, with no credential. That repository does not exist until it is published,
and reading a local sibling at a branch is not that read — the ref, the host and the absence of a
credential are all different. Nor does any of this prove that the index accepts the upload, that
the trusted-publishing relationship is configured on the index side, or that the `pypi`
environment demands a reviewer. The first of the four is answered by the first dispatch in CI
after the contract is published, the next two by the first real tag, and the last is a setting of
the repository, above.
