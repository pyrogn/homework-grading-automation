from github import Github
import hashlib
from github import Auth
import requests
import json
from tqdm import tqdm


auth = Auth.Token("YOUR_TOKEN")
g = Github(auth=auth)
org = g.get_organization("AI-DevTools24")


def SHA1(msg: str) -> str:
    return hashlib.sha1(msg.encode()).hexdigest()


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


def get_grade(passed_exercises):
    grade = 0
    # master task adds 0 -- skip it
    if "commit-one-file" in passed_exercises:
        grade += 0.5
    if "commit-one-file-staged" in passed_exercises:
        grade += 0.5
    if "ignore-them" in passed_exercises:
        grade += 0.5
    if "chase-branch" in passed_exercises:
        grade += 1
    if "merge-conflict" in passed_exercises:
        grade += 1
    if "save-your-work" in passed_exercises:
        grade += 1
    if "change-branch-history" in passed_exercises:
        grade += 1.5
    if "remove-ignored" in passed_exercises:
        grade += 1
    if "case-sensitive-filename" in passed_exercises:
        grade += 1
    if "fix-typo" in passed_exercises:
        grade += 1
    if "forge-date" in passed_exercises:
        grade += 1
    return grade


for repo in tqdm(org.get_repos(), total = org.get_repos().totalCount):
    result = {}
    result["grade"] = 0
    result["repo"] = repo.name
    branches = repo.get_branches()
    result["branch_exists"] = "task_01" in [branch.name for branch in branches]
    result["pull_request_exists"] = bool(repo.get_pulls().totalCount)
    contents = repo.get_contents(path="/")

    result_exists = False
    for file in contents:
        if file.name == "report.json":
            result_exists = True
            result_sha = file.sha
    check_files(result, contents)

    result["email_exists"] = False
    if result["branch_exists"]:
        contents = repo.get_contents(path="/", ref="task_01")
        check_files(result, contents)
        try:
            contents = repo.get_contents(path="/task_01_git", ref="task_01")
            for file in contents:
                if file.name == "gitexercises.email":
                    result["email_exists"] = True
                result["email"] = file.decoded_content.decode("utf8").strip()
                result["SHA1"] = SHA1(result["email"])
                passed_exercises = json.loads(
                    requests.get(
                        f"https://gitexercises.fracz.com/api/committer/{result['SHA1']}"
                    )
                    .content.decode("utf8")
                    .split("\n")[1]
                )["passedExercises"]
                result["grade"] = get_grade(passed_exercises)
        except:
            pass

    if not (
        result["gitignore_exists"]
        and result["pull_request_exists"]
        and result["license_exists"]
        and result["readme_exists"]
    ):
        result["grade"] = 0

    if result_exists:
        repo.update_file(
            "report.json",
            message="GRADE BOT",
            content=json.dumps(result, indent=4, ensure_ascii=False),
            sha=result_sha,
        )
    else:
        repo.create_file(
            "report.json",
            message="GRADE BOT",
            content=json.dumps(result, indent=4, ensure_ascii=False),
        )

g.close()
