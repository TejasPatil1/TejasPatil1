#!/usr/bin/env python3
"""
Fetch GitHub statistics, save them to stats.json, and rebuild profile.svg.

Needs a token in the GITHUB_TOKEN (or GH_STATS_TOKEN) environment variable.
Standard library only.  Usage:  python update_stats.py
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

API = "https://api.github.com"
TOKEN = os.environ.get("GH_STATS_TOKEN") or os.environ.get("GITHUB_TOKEN")
if not TOKEN:
    sys.exit("Set GH_STATS_TOKEN (or GITHUB_TOKEN) first - see README.")
HEAD = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json",
        "User-Agent": "profile-card-updater"}


def request(url, data=None):
    req = urllib.request.Request(url, data=data, headers=HEAD)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status, json.loads(r.read() or b"null")


def gql(query, **variables):
    body = json.dumps({"query": query, "variables": variables}).encode()
    _, res = request(f"{API}/graphql", body)
    if "errors" in res:
        sys.exit(f"GraphQL error: {res['errors']}")
    return res["data"]


def basic(login):
    q = """query($login:String!){ user(login:$login){
      createdAt followers{totalCount}
      repositoriesContributedTo(first:1, contributionTypes:[COMMIT,PULL_REQUEST,ISSUE,REPOSITORY]){totalCount}
      contributionsCollection{contributionYears} } }"""
    return gql(q, login=login)["user"]


def owned_repos(login):
    q = """query($login:String!,$cur:String){ user(login:$login){
      repositories(first:100, after:$cur, ownerAffiliations:OWNER){
        totalCount pageInfo{hasNextPage endCursor}
        nodes{nameWithOwner stargazerCount isFork isEmpty} } } }"""
    repos, cur = [], None
    while True:
        r = gql(q, login=login, cur=cur)["user"]["repositories"]
        repos += r["nodes"]
        if not r["pageInfo"]["hasNextPage"]:
            return r["totalCount"], repos
        cur = r["pageInfo"]["endCursor"]


def commits(login, created, years):
    q = """query($login:String!,$from:DateTime!,$to:DateTime!){ user(login:$login){
      contributionsCollection(from:$from,to:$to){totalCommitContributions restrictedContributionsCount} } }"""
    total = 0
    for y in years:
        c = gql(q, login=login, **{"from": f"{y}-01-01T00:00:00Z", "to": f"{y}-12-31T23:59:59Z"}
                )["user"]["contributionsCollection"]
        total += c["totalCommitContributions"] + c["restrictedContributionsCount"]
    return total


def loc(login, repos):
    """Lines added/deleted by `login` across owned, non-fork repos (stats/contributors)."""
    add = dele = 0
    for repo in repos:
        if repo["isFork"] or repo["isEmpty"]:
            continue
        url = f"{API}/repos/{repo['nameWithOwner']}/stats/contributors"
        for _ in range(6):  # GitHub returns 202 while it computes the stats
            try:
                status, data = request(url)
            except urllib.error.HTTPError as e:
                status, data = e.code, None
            if status == 200 and data:
                for c in data:
                    if c["author"] and c["author"]["login"].lower() == login.lower():
                        for w in c["weeks"]:
                            add += w["a"]
                            dele += w["d"]
                break
            if status != 202:
                break
            time.sleep(3)
    return add, dele


def main():
    login = json.load(open("config.json"))["github_username"]
    u = basic(login)
    total_repos, repos = owned_repos(login)
    add, dele = loc(login, repos)
    stats = {
        "repos": total_repos,
        "contributed": u["repositoriesContributedTo"]["totalCount"],
        "stars": sum(r["stargazerCount"] for r in repos),
        "commits": commits(login, u["createdAt"], u["contributionsCollection"]["contributionYears"]),
        "followers": u["followers"]["totalCount"],
        "loc_total": add - dele,
        "loc_add": add,
        "loc_del": dele,
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    with open("stats.json", "w") as f:
        json.dump(stats, f, indent=2)
    print(json.dumps(stats, indent=2))
    subprocess.run([sys.executable, "build_svg.py"], check=True)


if __name__ == "__main__":
    main()
