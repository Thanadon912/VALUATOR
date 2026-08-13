from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import re
import unittest
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


vercel_manage = load_module(
    "vercel_manage",
    PROJECT_ROOT / "scripts" / "vercel" / "manage.py",
)
supabase_production = load_module(
    "supabase_production",
    PROJECT_ROOT / "scripts" / "supabase" / "apply-production.py",
)


class DeploymentScriptTests(unittest.TestCase):
    def test_jenkins_jobs_target_current_github_repository(self) -> None:
        ci_config = (PROJECT_ROOT / "ops" / "jenkins" / "valuator-ci.xml").read_text(
            encoding="utf-8"
        )
        live_config = (
            PROJECT_ROOT / "ops" / "jenkins" / "valuator-live-e2e.xml"
        ).read_text(encoding="utf-8")

        self.assertIn("<repository>VALUATOR</repository>", ci_config)
        self.assertIn(
            "https://github.com/Thanadon912/VALUATOR</repositoryUrl>", ci_config
        )
        self.assertIn("https://github.com/Thanadon912/VALUATOR.git</url>", live_config)
        self.assertNotIn("VI-Stock-Analysis", ci_config + live_config)

    def test_jenkins_production_deploy_is_fail_closed(self) -> None:
        jenkinsfile = (PROJECT_ROOT / "Jenkinsfile").read_text(encoding="utf-8")
        backend_stage = re.search(
            r"stage\('Backend Tests'\).*?stage\('Frontend Lint'\)",
            jenkinsfile,
            re.DOTALL,
        )
        self.assertIsNotNone(backend_stage)
        self.assertNotIn("catchError", backend_stage.group(0))

        for stage_name in ("Deploy Staging", "Deploy Vercel Production"):
            stage = re.search(
                rf"stage\('{stage_name}'\) \{{(.*?)(?=\n    stage\(|\n  \}}\n\n  post)",
                jenkinsfile,
                re.DOTALL,
            )
            self.assertIsNotNone(stage)
            self.assertIn("branch 'main'", stage.group(1))
            self.assertIn(
                "expression { currentBuild.currentResult == 'SUCCESS' }",
                stage.group(1),
            )

    def test_first_deployment_confirms_framework_auto_detection(self) -> None:
        calls = []
        project = {
            "name": vercel_manage.BACKEND_PROJECT,
            "link": {"repoId": 12345},
        }

        def fake_api_request(_token, method, path, payload=None):
            calls.append((method, path, payload))
            return {"id": "deployment-id"}

        with patch.object(vercel_manage, "api_request", fake_api_request):
            result = vercel_manage.create_deployment(
                "token",
                project,
                "a" * 40,
            )

        self.assertEqual(result, {"id": "deployment-id"})
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(
            calls[0][1],
            "/v13/deployments?forceNew=1&skipAutoDetectionConfirmation=1",
        )
        self.assertEqual(calls[0][2]["gitSource"]["sha"], "a" * 40)

    def test_deploy_defers_staged_smoke_for_sso_but_verifies_production(self) -> None:
        revision = "a" * 40
        projects = {
            vercel_manage.BACKEND_PROJECT: {
                "id": "backend-project-id",
                "name": vercel_manage.BACKEND_PROJECT,
                "ssoProtection": {"deploymentType": "all_except_custom_domains"},
            },
            vercel_manage.FRONTEND_PROJECT: {
                "id": "frontend-project-id",
                "name": vercel_manage.FRONTEND_PROJECT,
                "ssoProtection": {"deploymentType": "all_except_custom_domains"},
            },
        }
        smoke_urls = []

        def fake_upsert(_token, name, _spec):
            return projects[name]

        def fake_create(_token, project, _revision):
            return {"id": "backend" if project["name"] == vercel_manage.BACKEND_PROJECT else "frontend"}

        def fake_ready(_token, deployment_id):
            return {"id": deployment_id, "url": f"{deployment_id}.preview.test"}

        def fake_wait(url, predicate, _description):
            smoke_urls.append(url)
            payload = {"status": "ok"} if url.endswith("/health") else {"revision": revision}
            self.assertTrue(predicate(payload))

        api_calls = []

        def fake_api_request(_token, method, path, payload=None):
            api_calls.append((method, path, payload))
            return {}

        with (
            patch.object(vercel_manage, "upsert_project", fake_upsert),
            patch.object(vercel_manage, "create_deployment", fake_create),
            patch.object(vercel_manage, "wait_ready", fake_ready),
            patch.object(vercel_manage, "api_request", fake_api_request),
            patch.object(vercel_manage, "http_json") as direct_smoke,
            patch.object(vercel_manage, "wait_for_payload", fake_wait),
        ):
            vercel_manage.deploy("token", revision)

        direct_smoke.assert_not_called()
        self.assertEqual(
            [call[1] for call in api_calls],
            [
                "/v10/projects/backend-project-id/promote/backend",
                "/v10/projects/frontend-project-id/promote/frontend",
            ],
        )
        self.assertEqual(
            smoke_urls,
            [
                f"{vercel_manage.BACKEND_URL}/health",
                f"{vercel_manage.FRONTEND_URL}/api/release",
            ],
        )

    def test_project_creation_sets_domain_policy_only_during_update(self) -> None:
        project = {
            "name": vercel_manage.FRONTEND_PROJECT,
            "rootDirectory": "Front-End",
            "framework": "nextjs",
            "autoAssignCustomDomains": False,
            "link": {
                "type": "github",
                "org": "Thanadon912",
                "repo": "VALUATOR",
            },
        }
        calls = []

        def fake_api_request(_token, method, path, payload=None):
            calls.append((method, path, payload))
            return project

        with (
            patch.object(vercel_manage, "get_project", return_value=None),
            patch.object(vercel_manage, "api_request", fake_api_request),
        ):
            result = vercel_manage.upsert_project(
                "token",
                vercel_manage.FRONTEND_PROJECT,
                {"rootDirectory": "Front-End", "framework": "nextjs"},
            )

        self.assertEqual(result, project)
        self.assertEqual(calls[0][0:2], ("POST", "/v10/projects"))
        self.assertNotIn("autoAssignCustomDomains", calls[0][2])
        self.assertEqual(calls[1][0:2], ("PATCH", "/v9/projects/valuator-thanadon912"))
        self.assertIs(calls[1][2]["autoAssignCustomDomains"], False)

    def test_gmail_smtp_runtime_values_are_backend_only(self) -> None:
        supplied = {
            "EMAIL_PROVIDER": "gmail_smtp",
            "EMAIL_INTERNAL_API_TOKEN": "internal-token",
            "SMTP_HOST": "smtp.gmail.com",
            "SMTP_PORT": "587",
            "SMTP_USERNAME": "sender@example.com",
            "SMTP_PASSWORD": "app-password",
            "EMAIL_FROM": "sender@example.com",
            "EMAIL_FROM_NAME": "VALUATOR",
        }

        backend = vercel_manage.runtime_values(vercel_manage.BACKEND_PROJECT, supplied)
        frontend = vercel_manage.runtime_values(vercel_manage.FRONTEND_PROJECT, supplied)

        self.assertEqual(backend["EMAIL_DELIVERY_MODE"], "smtp")
        self.assertEqual(backend["SMTP_PASSWORD"], "app-password")
        self.assertNotIn("SMTP_PASSWORD", frontend)
        self.assertNotIn("SMTP_USERNAME", frontend)

    def test_smtp_credentials_are_sensitive_vercel_values(self) -> None:
        for key in ("SMTP_PASSWORD", "SMTP_USERNAME", "EMAIL_FROM", "EMAIL_REPLY_TO"):
            with self.subTest(key=key):
                self.assertEqual(vercel_manage.env_payload(key, "value")["type"], "sensitive")
        self.assertEqual(
            vercel_manage.env_payload("SMTP_HOST", "smtp.gmail.com")["type"],
            "plain",
        )

    def test_supabase_request_identifies_client_and_keeps_token_in_header(self) -> None:
        captured = {}

        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

        def fake_urlopen(request, *, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return Response(json.dumps({"ok": True}).encode())

        with patch.object(supabase_production, "urlopen", fake_urlopen):
            result = supabase_production.request(
                "management-token",
                "GET",
                "/v1/projects",
            )

        request = captured["request"]
        self.assertEqual(result, {"ok": True})
        self.assertEqual(captured["timeout"], 60)
        self.assertEqual(request.get_header("Authorization"), "Bearer management-token")
        self.assertEqual(request.get_header("User-agent"), supabase_production.USER_AGENT)
        self.assertEqual(request.get_header("Accept"), "application/json")
        self.assertNotIn("management-token", request.full_url)


if __name__ == "__main__":
    unittest.main()
