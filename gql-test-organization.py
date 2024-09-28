import os
from dotenv import load_dotenv
from gql import gql, Client
from gql.transport.requests import RequestsHTTPTransport

load_dotenv()
github_token = os.getenv("GITHUB_TOKEN")

org_name = "test-organization12341234"

transport = RequestsHTTPTransport(
    url="https://api.github.com/graphql",
    headers={"Authorization": f"bearer {github_token}"},
    use_json=True,
)
client = Client(transport=transport, fetch_schema_from_transport=True)

query = gql("""
    query($org: String!, $cursor: String) {
      organization(login: $org) {
        repositories(first: 100, after: $cursor) {
          pageInfo {
            hasNextPage
            endCursor
          }
          nodes {
            name
            url
            licenseInfo {
              name
            }
            hasGitignore: object(expression: "HEAD:.gitignore") {
              id
            }
            hasReadme: object(expression: "HEAD:README.md") {
              id
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
            pullRequests(states: OPEN, first: 1, orderBy: {field: CREATED_AT, direction: DESC}) {
              nodes {
                number
                headRefName
                headRef {
                  name
                  target {
                    ... on Commit {
                      oid
                      emailFile: file(path: "task_01_git/gitexercises.email") {
                        object {
                          ... on Blob {
                            text
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
""")

# variables = {"owner": "AI-DevTools24", "name": "pro-1-git-pyrogn"}
has_next_page = True
cursor = None
all_repos = []
while has_next_page:
    variables = {"org": org_name, "cursor": cursor}

    result = client.execute(query, variable_values=variables)

    repos = result["organization"]["repositories"]["nodes"]
    all_repos.extend(repos)

    page_info = result["organization"]["repositories"]["pageInfo"]
    has_next_page = page_info["hasNextPage"]
    cursor = page_info["endCursor"]

for repo in all_repos:
    print(f"Repository: {repo['name']}")
    print(f"URL: {repo['url']}")
    print(f"License: {repo['licenseInfo']['name'] if repo['licenseInfo'] else 'None'}")
    print(f"Has .gitignore: {repo['hasGitignore'] is not None}")
    print(f"Has README.md: {repo['hasReadme'] is not None}")

    if repo["reportJson"]:
        print("report.json content:")
        print(repo["reportJson"]["text"])
    else:
        print("No report.json found")

    print("Branches:")
    for branch in repo["refs"]["nodes"]:
        print(f"  - {branch['name']}")

    if repo["pullRequests"]["nodes"]:
        pr = repo["pullRequests"]["nodes"][0]
        print(f"Latest PR: #{pr['number']} on branch {pr['headRefName']}")
        if pr["headRef"]["target"]["emailFile"]:
            print("Email file content:")
            print(pr["headRef"]["target"]["emailFile"]["object"]["text"])
        else:
            print("No email file found in the latest PR")
    else:
        print("No open pull requests")

    print("\n---\n")
