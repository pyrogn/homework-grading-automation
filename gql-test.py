import os
from dotenv import load_dotenv
from gql import gql, Client
from gql.transport.requests import RequestsHTTPTransport

load_dotenv()
github_token = os.getenv("GITHUB_TOKEN")

transport = RequestsHTTPTransport(
    url="https://api.github.com/graphql",
    headers={"Authorization": f"bearer {github_token}"},
    use_json=True,
)
client = Client(transport=transport, fetch_schema_from_transport=True)

query = gql("""
    query($owner: String!, $name: String!) {
      repository(owner: $owner, name: $name) {
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
""")

variables = {"owner": "AI-DevTools24", "name": "pro-1-git-pyrogn"}

result = client.execute(query, variable_values=variables)
print(result)

if result["repository"]["pullRequests"]["nodes"]:
    pr = result["repository"]["pullRequests"]["nodes"][0]
    email_file = pr["headRef"]["target"]["emailFile"]
    if email_file and email_file["object"]:
        email_content = email_file["object"]["text"]
        print(f"Email content: {email_content}")
    else:
        print("Email file not found in the PR")
else:
    print("No open pull requests found")

has_gitignore = result["repository"]["hasGitignore"] is not None
has_readme = result["repository"]["hasReadme"] is not None

print(f"Repository has .gitignore: {has_gitignore}")
print(f"Repository has README.md: {has_readme}")
