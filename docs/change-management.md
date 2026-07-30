# Change management

## Protected main branch

The GitHub repository applies the active ruleset **Main branch change control**
to the default branch. The ruleset:

- requires every change to arrive through a pull request;
- requires the pull request branch to be current with `main`;
- requires all review conversations to be resolved;
- rejects branch deletion and non-fast-forward updates;
- requires these checks:
  - `Repository and PowerShell validation`;
  - `Ansible, Compose and Prometheus validation`;
  - `Trivy repository security scan`.

The project currently has one maintainer, so the required approving review count
is zero. This preserves a usable solo-maintainer workflow while still enforcing
PR evidence, CI gates and an immutable change trail. A second maintainer should
raise the required approval count to one.

## Standard workflow

1. update local `main` with a fast-forward pull;
2. create a short-lived branch for one cohesive change;
3. implement and run the relevant local validations;
4. commit only files belonging to that change;
5. push the branch and open a draft pull request;
6. describe purpose, impact and validation evidence;
7. resolve failed checks and review conversations;
8. promote the pull request when it is ready;
9. use squash merge and remove the remote branch;
10. synchronize and prune the local repository.

Direct pushes, force pushes and deletion of `main` are prohibited.

## Emergency changes

There is no permanent bypass actor. An urgent change must still use a focused
pull request and the mandatory checks. If GitHub or CI is unavailable, preserve
the operational service using the documented rollback and recovery procedures;
do not silently weaken the repository ruleset.

Any temporary policy exception requires:

- explicit incident or change record;
- defined owner and expiration;
- restoration of the ruleset after recovery;
- sanitized evidence of the decision and validation.

## Automated dependency pull requests

Dependabot pull requests follow the same protected workflow. Passing checks do
not replace impact review for a major version update. Rebase the pull request
onto the current `main`, confirm the full CI matrix, then merge it separately
from functional changes.
