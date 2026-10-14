#!/usr/bin/env python3
# Copyright Advanced Micro Devices, Inc.
# SPDX-License-Identifier: MIT
"""
Check GitHub API access for all ROCm repos in a release plan.

Works for both branching and tagging. Reads the repo list from .gitmodules
via the GitHub API (no local clone needed). Accepts any valid git ref
(branch, tag, or SHA).

Verifies that the token can reach each repo via the API (a successful
response proves access — GitHub App installation tokens 404 on repos
outside their install grant, so no further `permissions.push`/`admin`
check is needed or meaningful for App tokens).

Can be run standalone to verify that the current machine (developer or CI)
has the necessary access before performing release activities.

Usage:
    python check_github_permissions.py \\
        --commitid <rock-git-ref> \\
        [--exclude-list repo1 repo2]
"""
import argparse
import logging
import sys
import urllib.error

from release_utils import (
    GITHUB_API,
    _api_request,
    extract_owner_repo,
    fetch_repo_map,
    get_gh_token,
)

def check_permissions(token: str, repo_map: dict[str, str]) -> int:
    """Check API access for every repo in repo_map.

    Returns 0 if all pass, 1 if any fail.
    """
    print("=" * 60)
    print(f"  GitHub Access Check")
    print(f"  Verifying access for {len(repo_map)} repo(s)")
    print("=" * 60)

    failed: dict[str, str] = {}

    for repo_name, url in repo_map.items():
        try:
            owner, repo = extract_owner_repo(url)
        except ValueError as exc:
            failed[repo_name] = f"URL parse error: {exc}"
            continue

        api_url = f"{GITHUB_API}/repos/{owner}/{repo}"
        try:
            data = _api_request(api_url, token)
        except urllib.error.HTTPError as exc:
            if exc.code == 403:
                failed[repo_name] = f"HTTP 403 Forbidden — token lacks access to {owner}/{repo}"
            elif exc.code == 404:
                failed[repo_name] = f"HTTP 404 — {owner}/{repo} not found (token may lack visibility)"
            else:
                failed[repo_name] = f"HTTP {exc.code} from GitHub API for {owner}/{repo}"
            continue
        except urllib.error.URLError as exc:
            failed[repo_name] = f"Network error checking {owner}/{repo}: {exc.reason}"
            continue

        # A successful response here already proves access: GitHub App
        # installation tokens can only see repos within their install grant
        # and get a 404 otherwise, so `permissions.push`/`admin` (which only
        # reflects human collaborator roles, not App installation scope) is
        # not a meaningful signal for App tokens and is intentionally not
        # checked here.
        print(f"[OK]  {repo_name}: {owner}/{repo} is accessible to this token")

    total = len(repo_map)
    passed = total - len(failed)
    print("=" * 60)
    print(f"  Passed : {passed} / {total} repo(s)")
    print(f"  Failed : {len(failed)} / {total} repo(s)")
    print("=" * 60)

    if failed:
        print(f"\nERROR: Access check failed for {len(failed)} repo(s). "
              "Aborting — insufficient access to proceed.")
        for name, reason in failed.items():
            print(f"  {name}: {reason}")
        return 1

    print("\nAll access checks passed.")
    return 0

def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check GitHub push/admin permissions for all ROCm repos in a release plan. "
            "Run this before creating branches or tags to verify the current machine "
            "has the necessary access."
        )
    )
    parser.add_argument(
        "-C", "--commitid",
        required=True,
        help="TheRock git ref (branch, tag, or SHA) to read .gitmodules from",
    )
    parser.add_argument(
        "--exclude-list",
        nargs="*",
        default=[],
        help="Repo names to skip",
    )
    parser.add_argument(
        "--include-list",
        nargs="*",
        default=[],
        help="If set, only check these repo names (all others skipped)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    token = get_gh_token()
    repo_map = fetch_repo_map(token, args.commitid, set(args.exclude_list))
    if args.include_list:
        include = set(args.include_list)
        repo_map = {name: url for name, url in repo_map.items() if name in include}
    return check_permissions(token, repo_map)

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
