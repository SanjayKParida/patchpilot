"""Fake GitHub App OAuth client. No network."""


class FakeGitHubAppClient:
    def __init__(self):
        self.users_by_code = {}
        self.fail_codes = set()
        self.installations = []
        self.repositories_by_installation = {}
        self.installation_tokens = {}
        self.exchanged = []
        self.listed_installations_for = []

        self.users_by_code["ok-code"] = {
            "id": 4242,
            "login": "octocat",
            "avatar_url": "https://github.com/octocat.png",
            "name": "The Octocat",
            "access_token": "ghu_user_token",
        }
        self.installations = [{"id": 77}]
        self.repositories_by_installation[77] = [
            {
                "id": 1,
                "name": "private-app",
                "full_name": "octocat/private-app",
                "private": True,
                "description": "secret",
                "html_url": "https://github.com/octocat/private-app",
                "default_branch": "main",
                "owner": {"login": "octocat"},
                "permissions": {"pull": True, "push": True, "admin": False},
            },
            {
                "id": 2,
                "name": "public-notes",
                "full_name": "octocat/public-notes",
                "private": False,
                "description": "notes",
                "html_url": "https://github.com/octocat/public-notes",
                "default_branch": "main",
                "owner": {"login": "octocat"},
                "permissions": {"pull": True, "push": False, "admin": False},
            },
        ]
        self.installation_tokens[77] = "ghs_installation_token"

    def authorization_url(self, *, state, code_challenge):
        return (
            "https://github.com/login/oauth/authorize"
            f"?client_id=iv1.test&state={state}&code_challenge={code_challenge}"
        )

    def installation_url(self, *, state):
        return (
            "https://github.com/apps/patchpilot-dev/installations/new"
            f"?state={state}"
        )

    def exchange_code(self, code, code_verifier):
        self.exchanged.append((code, code_verifier))
        if code in self.fail_codes or code not in self.users_by_code:
            from app.errors import AuthorizationFailed

            raise AuthorizationFailed("GitHub authorization failed (bad_verification_code)")
        user = self.users_by_code[code]
        return {
            "access_token": user["access_token"],
            "refresh_token": "ghr_refresh",
            "token_type": "bearer",
        }

    def get_authenticated_user(self, access_token):
        for user in self.users_by_code.values():
            if user["access_token"] == access_token:
                return {
                    "id": user["id"],
                    "login": user["login"],
                    "avatar_url": user["avatar_url"],
                    "name": user["name"],
                }
        return {"id": 1, "login": "unknown"}

    def list_installations(self, access_token):
        self.listed_installations_for.append(access_token)
        return list(self.installations)

    def list_installation_repositories(self, access_token, installation_id):
        return list(self.repositories_by_installation.get(installation_id, []))

    def create_installation_token(self, installation_id):
        token = self.installation_tokens.get(installation_id)
        if not token:
            from app.errors import UpstreamUnavailable

            raise UpstreamUnavailable("no installation token")
        return token
