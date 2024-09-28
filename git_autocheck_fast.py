import asyncio
import hashlib
import json
import logging
import os

import aiohttp
from dotenv import load_dotenv
from github import Github, GithubException
from gql import Client, gql
from gql.transport.requests import RequestsHTTPTransport


def setup_logger():
    logger = logging.getLogger("gradebot")
    logger.setLevel(logging.INFO)

    file_handler = logging.FileHandler("gradebot.log")
    file_handler.setLevel(logging.INFO)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


logger = setup_logger()

load_dotenv()

TOKEN = os.getenv("GITHUB_TOKEN")
CACHE_FILE = "completed_repos.json"
# ORG_NAME = "AI-DevTools24"
ORG_NAME = "test-organization12341234"
SOURCE_BRANCH_NAME = "task_01"
GITEXERCISES_MAX_CONCURRENT_REQUESTS = 5  # possibly no spam protection at our scale


def load_completed_repos():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            return set(json.load(f))
    return set()


def save_completed_repos(completed_repos):
    with open(CACHE_FILE, "w") as f:
        json.dump(sorted(completed_repos), f, indent=4, ensure_ascii=False)


completed_repos = load_completed_repos()
original_completed_repos = completed_repos.copy()

transport = RequestsHTTPTransport(
    url="https://api.github.com/graphql",
    headers={"Authorization": f"bearer {TOKEN}"},
    use_json=True,
)
client = Client(transport=transport, fetch_schema_from_transport=True)


semaphore = asyncio.Semaphore(GITEXERCISES_MAX_CONCURRENT_REQUESTS)


def sha1(msg: str) -> str:
    return hashlib.sha1(msg.encode()).hexdigest()


def get_grade(passed_exercises: list[str]) -> float:
    grade_map = {
        "commit-one-file": 0.5,
        "commit-one-file-staged": 0.5,
        "ignore-them": 0.5,
        "chase-branch": 1,
        "merge-conflict": 1,
        "save-your-work": 1,
        "change-branch-history": 1.5,
        "remove-ignored": 1,
        "case-sensitive-filename": 1,
        "fix-typo": 1,
        "forge-date": 1,
    }
    return sum(grade_map.get(exercise, 0) for exercise in passed_exercises)


async def fetch_committer_data(session: aiohttp.ClientSession, sha1: str) -> dict:
    url = f"https://gitexercises.fracz.com/api/committer/{sha1}"
    async with session.get(url) as response:
        data = await response.text()
        return json.loads(data.split("\n")[1])


async def process_repositories(repositories: list[dict]):
    async with aiohttp.ClientSession() as session:
        tasks = [
            process_repository(session, repo)
            for repo in repositories
            if repo["name"] not in completed_repos
        ]
        results = await asyncio.gather(*tasks)

        for result in results:
            if result["grade"] == 10:
                completed_repos.add(result["repo"])

        save_completed_repos(completed_repos)

        return results


def has_readme(repo: dict) -> bool:
    if "readmeFiles" in repo and "entries" in repo["readmeFiles"]:
        for entry in repo["readmeFiles"]["entries"]:
            if entry["type"] == "blob" and entry["name"].lower().startswith("readme"):
                return True
    return False


async def process_repository(session: aiohttp.ClientSession, repo: dict) -> dict:
    async with semaphore:
        result = {
            "grade": 0,
            "repo": repo["name"],
            "branch_exists": SOURCE_BRANCH_NAME
            in [branch["name"] for branch in repo["refs"]["nodes"]],
            "pull_request_exists": bool(repo["pullRequests"]["totalCount"]),
            "license_exists": repo["licenseInfo"] is not None,
            "gitignore_exists": repo["hasGitignore"] is not None,
            "readme_exists": has_readme(repo),
            "email_exists": False,
        }

        if result["branch_exists"]:
            email_file = repo["gitExercisesEmail"]
            if email_file:
                result["email_exists"] = True
                result["email"] = email_file["text"].strip()
                result["SHA1"] = sha1(result["email"])

        if all(
            [
                result["gitignore_exists"],
                result["pull_request_exists"],
                result["license_exists"],
                result["readme_exists"],
            ]
        ):
            committer_data = await fetch_committer_data(session, result["SHA1"])
            result["grade"] = get_grade(committer_data["passedExercises"])
        else:
            result["grade"] = 0

        return result


def update_reports(repositories, results):
    g = Github(TOKEN)

    for repo_name, repo in repositories.items():
        if repo["name"] in original_completed_repos:
            logger.info(f"Skipping {repo['name']} (already completed)")
            continue
        result = results.get(repo_name)
        try:
            existing_report = repo.get("reportJson")

            if existing_report:
                existing_content = json.loads(existing_report["text"])
                if existing_content == result:
                    logger.info(f"No changes for {repo['name']}, skipping...")
                    continue

            github_repo = g.get_repo(f"{ORG_NAME}/{repo['name']}")
            content = json.dumps(result, indent=4, ensure_ascii=False)

            try:
                file = github_repo.get_contents("report.json")

                github_repo.update_file(
                    path="report.json",
                    message="GRADE BOT: Update report",
                    content=content,
                    sha=file.sha,
                    branch="main",
                )
                logger.info(f"Updated report for {repo['name']}")
            except GithubException as e:
                if e.status == 404:
                    github_repo.create_file(
                        path="report.json",
                        message="GRADE BOT: Create report",
                        content=content,
                        branch="main",
                    )
                    logger.info(f"Created report for {repo['name']}")
                else:
                    raise
        except Exception as e:
            logger.error(f"Error updating report for {repo['name']}: {str(e)}")


def list_to_dict(lst, key_col):
    return {item[key_col]: item for item in lst}


async def main():
    query = gql("""
        query($org: String!, $cursor: String, $branch: String!) {
          organization(login: $org) {
            repositories(first: 50, after: $cursor) {
              pageInfo {
                hasNextPage
                endCursor
              }
              nodes {
                name
                url
                defaultBranchRef {
                target {
                    oid
                  }
                }
                licenseInfo {
                  name
                }
                hasGitignore: object(expression: "HEAD:.gitignore") {
                  id
                }
                readmeFiles: object(expression: "HEAD:") {
                  ... on Tree {
                    entries {
                      name
                      type
                    }
                  }
                }
                reportJson: object(expression: "HEAD:report.json") {
                  ... on Blob {
                    text
                  }
                }
                refs(refPrefix: "refs/heads/", first: 100) {
                  nodes {
                    name
                  }
                }
                gitExercisesEmail: object(expression: $branch) {
                  ... on Blob {
                    text
                  }
                }
                pullRequests(states: OPEN) {
                  totalCount
                }
              }
            }
          }
        }
    """)

    all_repos = []
    has_next_page = True
    cursor = None

    while has_next_page:
        result = client.execute(
            query,
            variable_values={
                "org": ORG_NAME,
                "cursor": cursor,
                "branch": f"{SOURCE_BRANCH_NAME}:task_01_git/gitexercises.email",
            },
        )
        repos = result["organization"]["repositories"]["nodes"]
        all_repos.extend(repos)
        page_info = result["organization"]["repositories"]["pageInfo"]
        has_next_page = page_info["hasNextPage"]
        cursor = page_info["endCursor"]

    results = await process_repositories(all_repos)

    # must be synchronous to respect GitHub's limits
    update_reports(list_to_dict(all_repos, "name"), list_to_dict(results, "repo"))


if __name__ == "__main__":
    asyncio.run(main())
