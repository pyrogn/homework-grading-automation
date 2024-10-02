import hashlib
import logging
import os
import json
import aiohttp
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from githubkit import GitHub
from githubkit.exception import GitHubException
from githubkit.webhooks import parse  # noqa
import base64


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


def check_files(result, contents):
    result["license_exists"] = (
        True
        if result.get("license_exists", False)
        else "LICENSE" in [file.name.upper().split(".")[0] for file in contents]
    )
    result["gitignore_exists"] = (
        True
        if result.get("gitignore_exists", False)
        else ".gitignore" in [file.name for file in contents]
    )
    result["readme_exists"] = (
        True
        if result.get("readme_exists", False)
        else "README" in [file.name.upper().split(".")[0] for file in contents]
    )


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


repo_last_processed = {}

app = FastAPI()
github = GitHub(
    TOKEN,
    base_url="https://api.github.com/",
    accept_format="full+json",
    previews=["starfox"],
    user_agent="GitHubKit/Python",
    follow_redirects=True,
    timeout=None,
    http_cache=True,
    auto_retry=True,
)
resp = github.rest.users.get_authenticated()
user = resp.parsed_data.login
print("I am", user)


async def process_repository(repo_data):
    current_repo = dict(owner=repo_data["owner"]["login"], repo=repo_data["name"])
    # repo_full_name = repo_data.full_name
    # current_time = time.time()
    # if repo_full_name in repo_last_processed:
    #     if current_time - repo_last_processed[repo_full_name] < 60:
    #         print(f"Skipping {repo_full_name}: processed too recently")
    #         return None
    result = {"grade": 0, "repo": repo_data["name"]}

    # Get branches
    branches_resp = await github.rest.repos.async_list_branches(**current_repo)
    result["branch_exists"] = "task_01" in [
        branch.name for branch in branches_resp.parsed_data
    ]

    # Get pull requests
    pulls_resp = await github.rest.pulls.async_list(**current_repo)
    result["pull_request_exists"] = len(pulls_resp.parsed_data) > 0

    # Get contents
    contents_resp = await github.rest.repos.async_get_content(path="", **current_repo)
    contents = contents_resp.parsed_data

    result_exists = False
    result_sha = None
    for file in contents:
        if file.name == "report.json":
            result_exists = True
            result_sha = file.sha

    check_files(result, contents)

    result["email_exists"] = False
    if result["branch_exists"]:
        try:
            task_contents_resp = await github.rest.repos.async_get_content(
                **current_repo,
                path="/task_01_git",
                ref="task_01",
            )
            task_contents = task_contents_resp.parsed_data
            for file in task_contents:
                if file.name == "gitexercises.email":
                    result["email_exists"] = True
                    email_content_resp = await github.rest.repos.async_get_content(
                        **current_repo,
                        path=file.path,
                        ref="task_01",
                    )
                    result["email"] = (
                        base64.b64decode(email_content_resp.parsed_data.content)
                        .decode("utf-8")
                        .strip()
                    )
                    result["SHA1"] = sha1(result["email"])

                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            f"https://gitexercises.fracz.com/api/committer/{result['SHA1']}"
                        ) as response:
                            data = await response.text()
                            passed_exercises = json.loads(data.split("\n")[1])[
                                "passedExercises"
                            ]

                    result["grade"] = get_grade(passed_exercises)
                    break
        except GitHubException:
            pass

    if not (
        result["gitignore_exists"]
        and result["pull_request_exists"]
        and result["license_exists"]
        and result["readme_exists"]
    ):
        result["grade"] = 0

    content_str = json.dumps(result, indent=4, ensure_ascii=False)
    content_bytes = content_str.encode("utf-8")
    content_base64 = base64.b64encode(content_bytes).decode("utf-8")

    if result_exists:
        await github.rest.repos.async_create_or_update_file_contents(
            **current_repo,
            path="report.json",
            message="GRADE BOT",
            content=content_base64,
            sha=result_sha,
        )
    else:
        await github.rest.repos.async_create_or_update_file_contents(
            **current_repo,
            path="report.json",
            message="GRADE BOT",
            content=content_base64,
        )

    return result


@app.post("/")
async def receive_event(request: Request):
    payload = await request.json()
    payload = json.loads(payload["payload"])
    print(payload)
    repository_data = payload["repository"]

    result = await process_repository(repository_data)

    print(result)
    return JSONResponse(
        content={"message": "Event received and processed", "result": result}
    )


@app.get("/")
async def root():
    return {"message": "Server is running. Send POST requests to this endpoint."}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("git_autocheck_webhook:app", host="0.0.0.0", port=3000, reload=True)
